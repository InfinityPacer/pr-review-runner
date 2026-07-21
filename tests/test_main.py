import json

from pr_review_runner.config import Settings
from pr_review_runner.events import Route
from pr_review_runner.main import _run_description, _run_review, run


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
            "config.response_language": "ja-JP",
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

    assert captured == [("improve", settings.passthrough, "ja-JP")]


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


def test_review_passes_current_pull_discussion_to_upstream(monkeypatch) -> None:
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
        }
    )
    pull = {"head": {"sha": "abcdef1234567890"}, "changed_files": 1}
    captured: dict[str, str] = {}

    class ReviewApi:
        def get(self, path: str) -> dict:
            assert path == "repos/owner/repo/pulls/7"
            return pull

        def paginate(self, path: str) -> list[dict]:
            if path == "repos/owner/repo/issues/7/comments?per_page=100":
                return [
                    {
                        "id": 1,
                        "user": {"login": "maintainer", "type": "User"},
                        "body": "The declared dependency is already included transitively.",
                    }
                ]
            if path == "repos/owner/repo/pulls/7/comments?per_page=100":
                return []
            if path == "repos/owner/repo/pulls/7/files?per_page=100":
                return []
            if path == "repos/owner/repo/pulls/7/reviews?per_page=100":
                return []
            raise AssertionError(path)

        def review_thread_resolutions(self, repository: str, number: int) -> dict[int, bool]:
            assert (repository, number) == ("owner/repo", 7)
            return {}

        def post(self, path: str, payload: dict) -> None:
            assert path == "repos/owner/repo/pulls/7/reviews"
            assert payload["event"] == "COMMENT"

        def delete(self, path: str) -> None:
            raise AssertionError(path)

    def fake_run_upstream(command, current, model_route, language, discussion):
        assert command == "review"
        assert current is settings
        assert model_route is settings.manual_review
        assert language == "zh-CN"
        captured["discussion"] = discussion
        return {"review": {"review_summary": "本次变更无需提出审查意见。"}}

    monkeypatch.setattr("pr_review_runner.main.run_upstream", fake_run_upstream)

    _run_review(ReviewApi(), settings, Route(7, "/review", False), pull, "zh-CN")

    assert "The declared dependency is already included transitively." in captured["discussion"]


def test_description_updates_summary_when_body_and_head_are_unchanged(monkeypatch) -> None:
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
        }
    )
    pull = {
        "body": "Contributor description.",
        "changed_files": 1,
        "head": {"sha": "abcdef1234567890"},
    }

    class DescriptionApi:
        def __init__(self) -> None:
            self.payloads: list[dict] = []

        def get(self, path: str) -> dict:
            assert path == "repos/owner/repo/pulls/7"
            return pull

        def patch(self, path: str, payload: dict) -> None:
            assert path == "repos/owner/repo/pulls/7"
            self.payloads.append(payload)

    api = DescriptionApi()
    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda *_: {"description": {"summary": "Generated summary."}},
    )

    _run_description(api, settings, Route(7, "/describe", False), pull, "en-US", "PR-Agent Summary")

    assert len(api.payloads) == 1
    assert api.payloads[0]["body"].startswith("Contributor description.")
    assert "Generated summary." in api.payloads[0]["body"]


def test_description_skips_summary_when_contributor_body_changes(monkeypatch, capsys) -> None:
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
        }
    )
    original = {"body": "Original body.", "changed_files": 1, "head": {"sha": "abcdef"}}
    current = {"body": "Contributor's new body.", "changed_files": 1, "head": {"sha": "abcdef"}}

    class DescriptionApi:
        def get(self, path: str) -> dict:
            assert path == "repos/owner/repo/pulls/7"
            return current

        def patch(self, path: str, payload: dict) -> None:
            raise AssertionError((path, payload))

    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda *_: {"description": {"summary": "Stale summary."}},
    )

    _run_description(DescriptionApi(), settings, Route(7, "/describe", False), original, "en-US", "PR-Agent Summary")

    assert "description changed during analysis" in capsys.readouterr().out


def test_description_skips_summary_when_head_changes(monkeypatch, capsys) -> None:
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
        }
    )
    original = {"body": "Original body.", "changed_files": 1, "head": {"sha": "old-head"}}
    current = {"body": "Original body.", "changed_files": 1, "head": {"sha": "new-head"}}

    class DescriptionApi:
        def get(self, path: str) -> dict:
            assert path == "repos/owner/repo/pulls/7"
            return current

        def patch(self, path: str, payload: dict) -> None:
            raise AssertionError((path, payload))

    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda *_: {"description": {"summary": "Stale summary."}},
    )

    _run_description(DescriptionApi(), settings, Route(7, "/describe", False), original, "en-US", "PR-Agent Summary")

    assert "head changed during description analysis" in capsys.readouterr().out


def test_zero_file_description_removes_owned_summary_without_model_call(monkeypatch) -> None:
    settings = Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
        }
    )
    body = (
        "Contributor description.\n\n## PR-Agent Summary\n\n"
        "<!-- pr-agent-summary:start -->\nOld summary.\n<!-- pr-agent-summary:end -->\n"
    )
    pull = {"body": body, "changed_files": 0, "head": {"sha": "abcdef"}}

    class DescriptionApi:
        def __init__(self) -> None:
            self.payload: dict | None = None

        def get(self, path: str) -> dict:
            assert path == "repos/owner/repo/pulls/7"
            return pull

        def patch(self, path: str, payload: dict) -> None:
            assert path == "repos/owner/repo/pulls/7"
            self.payload = payload

    api = DescriptionApi()
    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda *_: (_ for _ in ()).throw(AssertionError("zero-file descriptions must not call the model")),
    )

    _run_description(api, settings, Route(7, "/describe", False), pull, "en-US", "PR-Agent Summary")

    assert api.payload == {"body": "Contributor description."}
