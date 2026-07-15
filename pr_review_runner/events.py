"""GitHub event routing and repository policy guards."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Settings

AUTOMATIC_ACTIONS = {"opened", "reopened", "ready_for_review", "review_requested", "synchronize"}
COMMAND_PATTERN = re.compile(r"^/[a-z0-9_-]+(?=$|\s)", re.IGNORECASE)
# Equivalent upstream spellings share runner ownership and command-denylist semantics.
COMMAND_ALIASES = {
    "/auto_review": "/review",
    "/review_pr": "/review",
    "/describe_pr": "/describe",
    "/ask_question": "/ask",
    "/improve_code": "/improve",
    "/settings": "/config",
}


def canonical_command(command: str) -> str:
    """Normalize one upstream command or alias to its policy identity."""
    normalized = f"/{command.strip().lstrip('/').lower()}" if command.strip() else ""
    return COMMAND_ALIASES.get(normalized, normalized)


@dataclass(frozen=True)
class Route:
    """One accepted automatic event or manual PR command."""

    pull_number: int
    command: str
    automatic: bool


def route_event(event: dict, settings: Settings) -> Route | None:
    """Apply event, sender, command, and role gates before any model call."""
    if event.get("sender", {}).get("type") == "Bot":
        return None
    if settings.event_name in {"pull_request", "pull_request_target"}:
        if event.get("action") not in AUTOMATIC_ACTIONS:
            return None
        number = int(event.get("pull_request", {}).get("number") or event.get("number") or 0)
        return Route(number, "automatic", True) if number > 0 else None
    if settings.event_name != "issue_comment" or event.get("action") not in {"created", "edited"}:
        return None
    issue = event.get("issue") or {}
    if not issue.get("pull_request"):
        return None
    comment = event.get("comment") or {}
    if comment.get("author_association") not in settings.allowed_associations:
        return None
    body = str(comment.get("body") or "").strip()
    match = COMMAND_PATTERN.match(body)
    command = canonical_command(match.group(0)) if match else ""
    disabled_commands = {canonical_command(item) for item in settings.disabled_commands}
    if command in disabled_commands:
        return None
    number = int(issue.get("number") or 0)
    return Route(number, command, False) if command and number > 0 else None


def should_skip_pull(pull: dict, settings: Settings, route: Route) -> bool:
    """Apply auto scope, label, and title policies to every accepted route."""
    labels = {
        str(label.get("name") or "").strip().lower() for label in pull.get("labels") or [] if isinstance(label, dict)
    }
    if settings.skip_label in labels:
        return True
    if re.search(settings.skip_title_pattern, str(pull.get("title") or "")):
        return True
    if not route.automatic:
        return False
    if settings.auto_review_scope == "manual":
        return True
    head_repo = str(pull.get("head", {}).get("repo", {}).get("full_name") or "")
    return settings.auto_review_scope == "forks" and head_repo == settings.repository
