"""Validated runtime configuration for the container entrypoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ASSOCIATIONS = (
    "OWNER",
    "MEMBER",
    "COLLABORATOR",
    "CONTRIBUTOR",
    "FIRST_TIME_CONTRIBUTOR",
)


def _first(environment: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = environment.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _json_strings(raw: str, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must be a JSON array of strings") from error
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        qualifier = "a JSON array" if allow_empty else "a non-empty JSON array"
        raise ValueError(f"{name} must be {qualifier} of strings")
    return tuple(item.strip() for item in value)


def _normalize_command(command: str) -> str:
    return f"/{command.strip().lstrip('/').lower()}"


@dataclass(frozen=True)
class ModelRoute:
    """Model and reasoning effort used for one public command route."""

    model: str
    reasoning_effort: str


@dataclass(frozen=True)
class Settings:
    """Stable environment contract consumed by the runner."""

    repository: str
    event_name: str
    event_path: Path
    github_token: str
    describe: ModelRoute
    automatic_review: ModelRoute
    manual_review: ModelRoute
    ask: ModelRoute
    passthrough: ModelRoute
    fallback_models: tuple[str, ...]
    custom_model_max_tokens: int
    ai_timeout: int
    auto_review_scope: str
    allowed_associations: tuple[str, ...]
    disabled_commands: tuple[str, ...]
    skip_label: str
    skip_title_pattern: str
    max_findings: int
    response_language: str

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> Settings:
        """Build settings from GitHub Actions variables and documented overrides."""
        env = dict(os.environ if environment is None else environment)
        repository = _first(env, "GITHUB_REPOSITORY")
        event_name = _first(env, "GITHUB_EVENT_NAME")
        event_path = Path(_first(env, "GITHUB_EVENT_PATH"))
        github_token = _first(env, "GITHUB_TOKEN", "GH_TOKEN")
        missing = [
            name
            for name, value in (
                ("GITHUB_REPOSITORY", repository),
                ("GITHUB_EVENT_NAME", event_name),
                ("GITHUB_EVENT_PATH", str(event_path)),
                ("GITHUB_TOKEN", github_token),
            )
            if not value or value == "."
        ]
        if missing:
            raise ValueError(f"missing required environment variables: {', '.join(missing)}")

        fallback_models = _json_strings(
            _first(env, "PRR_FALLBACK_MODELS", default='["gpt-5.5", "gpt-5.4"]'),
            "PRR_FALLBACK_MODELS",
        )
        associations = _json_strings(
            _first(env, "PRR_ALLOWED_ASSOCIATIONS", default=json.dumps(DEFAULT_ASSOCIATIONS)),
            "PRR_ALLOWED_ASSOCIATIONS",
        )
        disabled_commands = tuple(
            _normalize_command(command)
            for command in _json_strings(
                _first(env, "PRR_DISABLED_COMMANDS", default="[]"),
                "PRR_DISABLED_COMMANDS",
                allow_empty=True,
            )
        )
        auto_scope = _first(env, "PRR_AUTO_REVIEW_SCOPE", default="all").lower()
        if auto_scope not in {"all", "forks", "manual"}:
            raise ValueError("PRR_AUTO_REVIEW_SCOPE must be all, forks, or manual")

        max_tokens = int(_first(env, "PRR_CUSTOM_MODEL_MAX_TOKENS", default="1050000"))
        ai_timeout = int(_first(env, "PRR_AI_TIMEOUT", default="900"))
        max_findings = int(_first(env, "PRR_MAX_FINDINGS", default="4"))
        if min(max_tokens, ai_timeout, max_findings) < 1:
            raise ValueError("numeric PRR settings must be positive")

        return cls(
            repository=repository,
            event_name=event_name,
            event_path=event_path,
            github_token=github_token,
            describe=ModelRoute(
                _first(env, "PRR_DESCRIBE_MODEL", default="gpt-5.6-terra"),
                _first(env, "PRR_DESCRIBE_REASONING_EFFORT", default="medium"),
            ),
            automatic_review=ModelRoute(
                _first(env, "PRR_AUTO_REVIEW_MODEL", default="gpt-5.6-sol"),
                _first(env, "PRR_AUTO_REVIEW_REASONING_EFFORT", default="xhigh"),
            ),
            manual_review=ModelRoute(
                _first(env, "PRR_MANUAL_REVIEW_MODEL", default="gpt-5.6-sol"),
                _first(env, "PRR_MANUAL_REVIEW_REASONING_EFFORT", default="xhigh"),
            ),
            ask=ModelRoute(
                _first(env, "PRR_ASK_MODEL", default="gpt-5.6-terra"),
                _first(env, "PRR_ASK_REASONING_EFFORT", default="high"),
            ),
            passthrough=ModelRoute(
                _first(env, "PRR_PASSTHROUGH_MODEL", default="gpt-5.6-sol"),
                _first(env, "PRR_PASSTHROUGH_REASONING_EFFORT", default="xhigh"),
            ),
            fallback_models=fallback_models,
            custom_model_max_tokens=max_tokens,
            ai_timeout=ai_timeout,
            auto_review_scope=auto_scope,
            allowed_associations=associations,
            disabled_commands=disabled_commands,
            skip_label=_first(env, "PRR_SKIP_LABEL", default="skip pr-agent").lower(),
            skip_title_pattern=_first(env, "PRR_SKIP_TITLE_PATTERN", default=r"^(?:\[Auto\]|Auto)"),
            max_findings=max_findings,
            response_language=_first(env, "config.response_language"),
        )
