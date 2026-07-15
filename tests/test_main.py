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
            "OPENAI_KEY": "api-key",
            "OPENAI_API_BASE": "https://example.test/v1",
        }
    )
    captured: list[tuple[str, object, str]] = []

    monkeypatch.setattr("pr_review_runner.main.GitHubApi", lambda *_: PullApi())
    monkeypatch.setattr(
        "pr_review_runner.main.run_upstream",
        lambda command, current, route, language: captured.append((command, route, language)),
    )

    run(settings)

    assert captured == [("improve", settings.passthrough, "en-US")]
