import json

from pr_review_runner.config import Settings
from pr_review_runner.main import run


class PullApi:
    """Minimal GitHub API contract needed before a manual command is delegated."""

    def get(self, path: str) -> dict:
        assert path == "repos/owner/repo/pulls/7"
        return {
            "title": "Improve this implementation",
            "body": "Please suggest concrete code changes for this pull request.",
            "labels": [],
            "head": {"repo": {"full_name": "owner/repo"}},
        }


def test_unowned_slash_command_passes_through_with_full_event(monkeypatch, tmp_path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "created",
                "sender": {"type": "User"},
                "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
                "comment": {"body": "/improve --extended", "author_association": "OWNER"},
            }
        ),
        encoding="utf-8",
    )
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_TOKEN": "github-token",
        }
    )
    captured: list[tuple[str, object, str]] = []

    monkeypatch.setattr("pr_review_runner.main.GitHubApi", lambda *_: PullApi())
    monkeypatch.setattr("pr_review_runner.main.is_supported_upstream_command", lambda command: command == "improve")
    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda command, current, route, language: captured.append((command, route, language)),
    )

    run(settings)

    assert captured == [("improve", settings.passthrough, "en-US")]


def test_unknown_slash_command_is_rejected_before_github_or_upstream_calls(monkeypatch, tmp_path, capsys) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "created",
                "sender": {"type": "User"},
                "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
                "comment": {"body": "/reflect", "author_association": "OWNER"},
            }
        ),
        encoding="utf-8",
    )
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_TOKEN": "github-token",
        }
    )

    monkeypatch.setattr("pr_review_runner.main.is_supported_upstream_command", lambda command: False)
    monkeypatch.setattr(
        "pr_review_runner.main.GitHubApi",
        lambda *_: (_ for _ in ()).throw(AssertionError("GitHub API must not be called")),
    )
    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda *_: (_ for _ in ()).throw(AssertionError("upstream must not be called")),
    )

    run(settings)

    assert "not supported by the bundled PR-Agent" in capsys.readouterr().out


def test_review_alias_uses_runner_owned_native_review_route(monkeypatch, tmp_path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "created",
                "sender": {"type": "User"},
                "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
                "comment": {"body": "/review_pr --incremental", "author_association": "OWNER"},
            }
        ),
        encoding="utf-8",
    )
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_TOKEN": "github-token",
        }
    )
    captured = []

    monkeypatch.setattr("pr_review_runner.main.GitHubApi", lambda *_: PullApi())
    monkeypatch.setattr(
        "pr_review_runner.main.is_supported_upstream_command",
        lambda *_: (_ for _ in ()).throw(AssertionError("owned aliases must not use passthrough validation")),
    )
    monkeypatch.setattr(
        "pr_review_runner.main._run_review",
        lambda api, current, route, pull, language: captured.append((current, route, language)),
    )
    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda *_: (_ for _ in ()).throw(AssertionError("owned aliases must not use direct passthrough")),
    )

    run(settings)

    assert len(captured) == 1
    assert captured[0][0] is settings
    assert captured[0][1].command == "/review"
    assert captured[0][2] == "en-US"
