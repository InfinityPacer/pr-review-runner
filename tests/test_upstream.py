import json
from pathlib import Path

from pr_review_runner.config import Settings
from pr_review_runner.upstream import REVIEW_INSTRUCTIONS, run_upstream


def settings() -> Settings:
    return Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
            "OPENAI_KEY": "api-key",
            "OPENAI_API_BASE": "https://example.test/v1",
        }
    )


def test_review_subprocess_receives_route_defaults_and_structured_output(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_run(command, check, env):
        assert check is True
        assert command[-1].endswith("github_action_runner.py")
        captured.update(env)
        Path(env["GITHUB_OUTPUT"]).write_text(
            f"review={json.dumps({'key_issues_to_review': []})}\n",
            encoding="utf-8",
        )

    monkeypatch.setattr("pr_review_runner.upstream.subprocess.run", fake_run)
    current = settings()
    outputs = run_upstream("review", current, current.automatic_review, "zh-CN")

    assert outputs == {"review": {"key_issues_to_review": []}}
    assert captured["config.model"] == "gpt-5.6-sol"
    assert captured["config.reasoning_effort"] == "xhigh"
    assert captured["config.custom_model_max_tokens"] == "1050000"
    assert json.loads(captured["config.fallback_models"]) == ["gpt-5.5", "gpt-5.4"]
    assert captured["OPENAI.API_BASE"] == "https://example.test/v1"
    assert captured["GITHUB_REPOSITORY"] == "owner/repo"
    assert captured["GITHUB_EVENT_NAME"] == "pull_request_target"
    assert captured["GITHUB_EVENT_PATH"] == "/tmp/event.json"
    assert captured["config.publish_output"] == "false"
    assert captured["pr_reviewer.extra_instructions"] == REVIEW_INSTRUCTIONS


def test_describe_ask_and_passthrough_keep_independent_model_routes(monkeypatch) -> None:
    models: list[tuple[str, str]] = []

    def fake_run(command, check, env):
        models.append((env["config.model"], env["config.reasoning_effort"]))

    monkeypatch.setattr("pr_review_runner.upstream.subprocess.run", fake_run)
    current = settings()
    run_upstream("describe", current, current.describe, "en-US")
    run_upstream("ask", current, current.ask, "en-US")
    run_upstream("improve", current, current.passthrough, "en-US")

    assert models == [
        ("gpt-5.6-terra", "medium"),
        ("gpt-5.6-terra", "high"),
        ("gpt-5.6-sol", "xhigh"),
    ]
