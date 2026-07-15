import json

import pytest

from pr_review_runner.config import Settings


def base_environment() -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_EVENT_NAME": "pull_request_target",
        "GITHUB_EVENT_PATH": "/tmp/event.json",
        "GITHUB_TOKEN": "github-token",
    }


def test_model_routes_default_to_production_policy() -> None:
    settings = Settings.from_environment(base_environment())

    assert (settings.describe.model, settings.describe.reasoning_effort) == ("gpt-5.6-terra", "medium")
    assert (settings.automatic_review.model, settings.automatic_review.reasoning_effort) == ("gpt-5.6-sol", "xhigh")
    assert (settings.manual_review.model, settings.manual_review.reasoning_effort) == ("gpt-5.6-sol", "xhigh")
    assert (settings.ask.model, settings.ask.reasoning_effort) == ("gpt-5.6-terra", "high")
    assert (settings.passthrough.model, settings.passthrough.reasoning_effort) == ("gpt-5.6-sol", "xhigh")
    assert settings.fallback_models == ("gpt-5.5", "gpt-5.4")
    assert settings.custom_model_max_tokens == 1_050_000
    assert settings.disabled_commands == ()
    assert settings.response_language == ""


def test_model_routes_accept_independent_overrides() -> None:
    environment = base_environment() | {
        "PRR_DESCRIBE_MODEL": "describe-model",
        "PRR_AUTO_REVIEW_MODEL": "automatic-model",
        "PRR_MANUAL_REVIEW_MODEL": "manual-model",
        "PRR_ASK_MODEL": "ask-model",
        "PRR_PASSTHROUGH_MODEL": "passthrough-model",
        "PRR_FALLBACK_MODELS": json.dumps(["fallback-a", "fallback-b"]),
        "PRR_CUSTOM_MODEL_MAX_TOKENS": "123456",
        "PRR_DISABLED_COMMANDS": json.dumps(["improve", "/UPDATE_CHANGELOG"]),
        "config.response_language": "ja-JP",
    }

    settings = Settings.from_environment(environment)

    assert settings.describe.model == "describe-model"
    assert settings.automatic_review.model == "automatic-model"
    assert settings.manual_review.model == "manual-model"
    assert settings.ask.model == "ask-model"
    assert settings.passthrough.model == "passthrough-model"
    assert settings.fallback_models == ("fallback-a", "fallback-b")
    assert settings.custom_model_max_tokens == 123456
    assert settings.disabled_commands == ("/improve", "/update_changelog")
    assert settings.response_language == "ja-JP"


def test_invalid_scope_and_missing_runtime_context_fail_closed() -> None:
    with pytest.raises(ValueError, match="PRR_AUTO_REVIEW_SCOPE"):
        Settings.from_environment(base_environment() | {"PRR_AUTO_REVIEW_SCOPE": "unknown"})

    environment = base_environment()
    environment.pop("GITHUB_TOKEN")
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        Settings.from_environment(environment)
