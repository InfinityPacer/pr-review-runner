import json
from pathlib import Path
from types import SimpleNamespace

from pr_review_runner.config import Settings
from pr_review_runner.upstream import (
    REVIEW_INSTRUCTIONS,
    _review_prompt_with_summary,
    is_supported_upstream_command,
    run_upstream,
)


def settings() -> Settings:
    return Settings.from_environment(
        {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_EVENT_NAME": "pull_request_target",
            "GITHUB_EVENT_PATH": "/tmp/event.json",
            "GITHUB_TOKEN": "github-token",
        }
    )


def test_review_subprocess_receives_route_defaults_and_structured_output(monkeypatch) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setenv("ANTHROPIC.KEY", "provider-key")
    monkeypatch.setenv("OLLAMA.API_BASE", "https://provider.example.test")
    monkeypatch.setenv("CUSTOM_PROVIDER_OPTION", "provider-option")

    def fake_run(command, check, env):
        assert check is True
        assert command[-1].endswith("github_action_runner.py")
        captured.update(env)
        Path(env["GITHUB_OUTPUT"]).write_text(
            f"review={json.dumps({'key_issues_to_review': []})}\n",
            encoding="utf-8",
        )

    monkeypatch.setattr("pr_review_runner.upstream.subprocess.run", fake_run)
    monkeypatch.setattr("pr_review_runner.upstream._review_prompt_with_summary", lambda: "review prompt with summary")
    current = settings()
    discussion = '{"issue_comments":[{"author":"maintainer","body":"The dependency is already included."}]}'
    outputs = run_upstream("review", current, current.automatic_review, "zh-CN", discussion)

    assert outputs == {"review": {"key_issues_to_review": []}}
    assert captured["config.model"] == "gpt-5.6-sol"
    assert captured["config.reasoning_effort"] == "xhigh"
    assert captured["config.custom_model_max_tokens"] == "1050000"
    assert json.loads(captured["config.fallback_models"]) == ["gpt-5.5", "gpt-5.4"]
    assert captured["ANTHROPIC.KEY"] == "provider-key"
    assert captured["OLLAMA.API_BASE"] == "https://provider.example.test"
    assert captured["CUSTOM_PROVIDER_OPTION"] == "provider-option"
    assert captured["GITHUB_REPOSITORY"] == "owner/repo"
    assert captured["GITHUB_EVENT_NAME"] == "pull_request_target"
    assert captured["GITHUB_EVENT_PATH"] == "/tmp/event.json"
    assert captured["config.publish_output"] == "false"
    assert captured["pr_review_prompt.system"] == "review prompt with summary"
    assert captured["pr_reviewer.extra_instructions"].startswith(REVIEW_INSTRUCTIONS)
    assert "untrusted evidence" in captured["pr_reviewer.extra_instructions"]
    assert "The dependency is already included." in captured["pr_reviewer.extra_instructions"]


def test_review_prompt_extends_schema_and_example(tmp_path) -> None:
    prompt_file = tmp_path / "pr_reviewer_prompts.toml"
    prompt_file.write_text(
        '''[pr_review_prompt]
system="""class Review(BaseModel):
    key_issues_to_review: list

Example output:
```yaml
review:
  key_issues_to_review: []
```
"""
''',
        encoding="utf-8",
    )

    prompt = _review_prompt_with_summary(prompt_file)

    assert prompt.count("review_summary: str = Field(") == 1
    assert prompt.count("  review_summary: |") == 1
    assert "key_issues_to_review: list" in prompt


def test_describe_ask_and_passthrough_keep_independent_model_routes(monkeypatch) -> None:
    models: list[tuple[str, str]] = []
    description_instructions: list[str] = []

    def fake_run(command, check, env):
        models.append((env["config.model"], env["config.reasoning_effort"]))
        if env.get("github_action_config.auto_describe") == "true":
            description_instructions.append(env["pr_description.extra_instructions"])

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
    assert description_instructions == [
        "Your response MUST be written in the language corresponding to locale code: 'en-US'. This is crucial.\n"
        "Summarize the change goal, key implementation details, compatibility impact, tests, and\n"
        "notable risks.\n"
        "Use 2-4 bullets for small pull requests and 4-8 bullets for larger changes.\n"
        "Avoid file lists and local command transcripts."
    ]


def test_upstream_command_validation_uses_bundled_registry(monkeypatch) -> None:
    module = SimpleNamespace(commands=("review", "improve", "update_changelog"))
    monkeypatch.setattr("pr_review_runner.upstream.importlib.import_module", lambda name: module)

    assert is_supported_upstream_command("improve")
    assert is_supported_upstream_command("UPDATE_CHANGELOG")
    assert not is_supported_upstream_command("reflect")
