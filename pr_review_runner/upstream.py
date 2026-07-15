"""Run the pinned PR-Agent action with isolated per-command configuration."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import ModelRoute, Settings

UPSTREAM_RUNNER = "/app/pr_agent/servers/github_action_runner.py"
UPSTREAM_REVIEW_PROMPTS = Path("/app/pr_agent/settings/pr_reviewer_prompts.toml")
REVIEW_SCHEMA_ANCHOR = "class Review(BaseModel):\n"
REVIEW_EXAMPLE_ANCHOR = "Example output:\n```yaml\nreview:\n"
REVIEW_SUMMARY_FIELD = """    review_summary: str = Field(
        description="A concise natural-language summary of what the pull request changes and the overall review "
        "assessment. When findings exist, synthesize their severity, common behavioral impact, and overall risk. "
        "Do not list file names or line numbers, repeat individual issue descriptions, or invent concerns when "
        "key_issues_to_review is empty. When no findings exist, conclude naturally that there are no review comments."
    )
"""
REVIEW_SUMMARY_EXAMPLE = """  review_summary: |
    ...
"""
REVIEW_INSTRUCTIONS = """Return key_issues_to_review only for concrete behavior defects introduced by this pull request.
Each finding must identify the affected behavior, a reachable trigger, and the existing contract or invariant it
violates.
Use issue_content to state the smallest correction boundary, not a code patch.
Write review_summary as 1-3 natural sentences that summarize what the pull request changes and the overall review
assessment. When findings exist, synthesize their risk and common themes without copying issue_content or listing file
locations. When no findings exist, still summarize the change and conclude naturally that there are no review comments.
Prefix every issue_header with exactly one severity token: [HIGH], [MEDIUM], or [LOW].
Use [HIGH] for reachable data loss, security or authorization bypass, destructive side effects, or broad service
failure.
Use [MEDIUM] for concrete functional regressions, incorrect results, compatibility breaks, or bounded resource failures.
Use [LOW] for localized actionable defects with limited impact. Do not use a severity token for non-defects.
Do not report style preferences, comments, refactors, architecture alternatives, speculative races, extra hardening,
optional tests, or hypothetical concerns.
Return no findings when the evidence is incomplete."""
DESCRIPTION_INSTRUCTIONS = """Summarize the change goal, key implementation details, compatibility impact, tests, and
notable risks.
Use 2-4 bullets for small pull requests and 4-8 bullets for larger changes.
Avoid file lists and local command transcripts."""


def _review_prompt_with_summary(path: Path = UPSTREAM_REVIEW_PROMPTS) -> str:
    """Extend the pinned upstream review schema without adding another model call."""
    with path.open("rb") as handle:
        prompt = str(tomllib.load(handle)["pr_review_prompt"]["system"])
    if prompt.count(REVIEW_SCHEMA_ANCHOR) != 1 or prompt.count(REVIEW_EXAMPLE_ANCHOR) != 1:
        raise RuntimeError("Pinned PR-Agent review prompt no longer matches the summary extension anchors")
    prompt = prompt.replace(REVIEW_SCHEMA_ANCHOR, REVIEW_SCHEMA_ANCHOR + REVIEW_SUMMARY_FIELD, 1)
    return prompt.replace(REVIEW_EXAMPLE_ANCHOR, REVIEW_EXAMPLE_ANCHOR + REVIEW_SUMMARY_EXAMPLE, 1)


def _common_environment(settings: Settings, route: ModelRoute, language: str, output_path: str) -> dict[str, str]:
    # Provider credentials and endpoints retain the exact names expected by PR-Agent.
    environment = dict(os.environ)
    environment.update(
        {
            "GITHUB_REPOSITORY": settings.repository,
            "GITHUB_EVENT_NAME": settings.event_name,
            "GITHUB_EVENT_PATH": str(settings.event_path),
            "GITHUB_TOKEN": settings.github_token,
            "GITHUB_OUTPUT": output_path,
            "config.model": route.model,
            "config.fallback_models": json.dumps(settings.fallback_models),
            "config.custom_model_max_tokens": str(settings.custom_model_max_tokens),
            "config.reasoning_effort": route.reasoning_effort,
            "config.ai_timeout": str(settings.ai_timeout),
            "config.response_language": language,
            "config.large_patch_policy": "clip",
            "github_action_config.auto_review": "false",
            "github_action_config.auto_describe": "false",
            "github_action_config.auto_improve": "false",
            "github_action_config.pr_actions": '["opened", "reopened", "ready_for_review", "review_requested"]',
            "github_action_config.handle_push_trigger": "true",
        }
    )
    return environment


def is_supported_upstream_command(command: str) -> bool:
    """Check a passthrough command against the bundled PR-Agent registry."""
    module = importlib.import_module("pr_agent.agent.pr_agent")
    registered = getattr(module, "commands", ())
    normalized = command.strip().lstrip("/").lower()
    return normalized in {str(item).strip().lower() for item in registered}


def _read_outputs(path: Path) -> dict[str, object]:
    outputs: dict[str, object] = {}
    if not path.exists():
        return outputs
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            outputs[key] = json.loads(value)
    return outputs


def run_upstream(command: str, settings: Settings, route: ModelRoute, language: str) -> dict[str, object]:
    """Execute one upstream action command in a fresh process and capture outputs."""
    with NamedTemporaryFile(prefix="pr-review-runner-output-", delete=False) as handle:
        output_path = Path(handle.name)
    try:
        environment = _common_environment(settings, route, language, str(output_path))
        if command == "describe":
            environment.update(
                {
                    "github_action_config.auto_describe": "true",
                    "github_action_config.push_commands": '["/describe"]',
                    "pr_description.generate_ai_title": "false",
                    "pr_description.publish_labels": "false",
                    "pr_description.publish_description_as_comment": "false",
                    "pr_description.publish_description_as_comment_persistent": "false",
                    "pr_description.enable_pr_diagram": "false",
                    "pr_description.enable_pr_type": "false",
                    "pr_description.enable_help_text": "false",
                    "pr_description.enable_help_comment": "false",
                    "pr_description.enable_semantic_files_types": "false",
                    "pr_description.collapsible_file_list": "adaptive",
                    "pr_description.add_original_user_description": "true",
                    "pr_description.use_description_markers": "true",
                    "pr_description.final_update_message": "false",
                    "pr_description.extra_instructions": (
                        "Your response MUST be written in the language corresponding to locale code: "
                        f"'{language}'. This is crucial.\n{DESCRIPTION_INSTRUCTIONS}"
                    ),
                }
            )
        elif command == "review":
            environment.update(
                {
                    "config.publish_output": "false",
                    "pr_review_prompt.system": _review_prompt_with_summary(),
                    "github_action_config.auto_review": "true",
                    "github_action_config.push_commands": '["/review"]',
                    "github_action_config.enable_output": "true",
                    "pr_reviewer.num_max_findings": str(settings.max_findings),
                    "pr_reviewer.require_score_review": "false",
                    "pr_reviewer.require_tests_review": "false",
                    "pr_reviewer.require_security_review": "false",
                    "pr_reviewer.require_estimate_effort_to_review": "false",
                    "pr_reviewer.require_estimate_contribution_time_cost": "false",
                    "pr_reviewer.require_can_be_split_review": "false",
                    "pr_reviewer.require_todo_scan": "false",
                    "pr_reviewer.require_ticket_analysis_review": "false",
                    "pr_reviewer.enable_review_labels_effort": "false",
                    "pr_reviewer.enable_review_labels_security": "false",
                    "pr_reviewer.extra_instructions": REVIEW_INSTRUCTIONS,
                }
            )
        subprocess.run([sys.executable, UPSTREAM_RUNNER], check=True, env=environment)
        return _read_outputs(output_path)
    finally:
        output_path.unlink(missing_ok=True)
