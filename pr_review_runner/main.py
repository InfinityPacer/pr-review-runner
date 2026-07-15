"""Container entrypoint for event routing, analysis, and publication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import __version__
from .config import Settings
from .description import prepare_body, remove_unfilled_body, response_language
from .events import Route, route_event, should_skip_pull
from .github import GitHubApi
from .review import legacy_summary_comment_ids, render_review_payload
from .upstream import run_upstream


def _load_event(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        event = json.load(handle)
    if not isinstance(event, dict):
        raise ValueError("GITHUB_EVENT_PATH must contain a JSON object")
    return event


def _patch_body(api: GitHubApi, repository: str, number: int, current: str, updated: str) -> None:
    if updated != current:
        api.patch(f"repos/{repository}/pulls/{number}", {"body": updated})


def _run_description(api: GitHubApi, settings: Settings, route: Route, pull: dict, language: str, heading: str) -> None:
    body = str(pull.get("body") or "")
    prepared = prepare_body(body, heading, int(pull.get("changed_files") or 0))
    _patch_body(api, settings.repository, route.pull_number, body, prepared)
    if int(pull.get("changed_files") or 0) == 0:
        return
    try:
        run_upstream("describe", settings, settings.describe, language)
    finally:
        refreshed = api.get(f"repos/{settings.repository}/pulls/{route.pull_number}")
        refreshed_body = str(refreshed.get("body") or "")
        cleaned = remove_unfilled_body(refreshed_body)
        _patch_body(api, settings.repository, route.pull_number, refreshed_body, cleaned)


def _run_review(api: GitHubApi, settings: Settings, route: Route, pull: dict, language: str) -> None:
    reviewed_head = str(pull.get("head", {}).get("sha") or "")
    model_route = settings.automatic_review if route.automatic else settings.manual_review
    outputs = run_upstream("review", settings, model_route, language)
    review = outputs.get("review")
    changed_files = int(pull.get("changed_files") or 0)
    if not isinstance(review, dict):
        if changed_files:
            raise RuntimeError("review analysis produced no structured output for a non-empty pull request")
        review = {}

    current = api.get(f"repos/{settings.repository}/pulls/{route.pull_number}")
    if str(current.get("head", {}).get("sha") or "") != reviewed_head:
        print("PR head changed during analysis; skipping stale review publication.")
        return
    files = api.paginate(f"repos/{settings.repository}/pulls/{route.pull_number}/files?per_page=100")
    comments = api.paginate(f"repos/{settings.repository}/pulls/{route.pull_number}/comments?per_page=100")
    reviews = api.paginate(f"repos/{settings.repository}/pulls/{route.pull_number}/reviews?per_page=100")
    payload = render_review_payload(review, files, comments, reviews, settings.repository, reviewed_head, language)

    latest = api.get(f"repos/{settings.repository}/pulls/{route.pull_number}")
    if str(latest.get("head", {}).get("sha") or "") != reviewed_head:
        print("PR head changed while rendering; skipping stale review publication.")
        return
    if payload:
        api.post(f"repos/{settings.repository}/pulls/{route.pull_number}/reviews", payload)
    issue_comments = api.paginate(f"repos/{settings.repository}/issues/{route.pull_number}/comments?per_page=100")
    for comment_id in legacy_summary_comment_ids(issue_comments):
        api.delete(f"repos/{settings.repository}/issues/comments/{comment_id}")


def run(settings: Settings) -> None:
    """Handle one GitHub event without checking out or executing PR code."""
    event = _load_event(settings.event_path)
    route = route_event(event, settings)
    if route is None:
        print("Event does not match a supported PR review route; skipping.")
        return
    api = GitHubApi(settings.github_token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    pull = api.get(f"repos/{settings.repository}/pulls/{route.pull_number}")
    if should_skip_pull(pull, settings, route):
        print("Pull request matches the configured skip policy; skipping.")
        return
    language, heading = response_language(pull)
    if route.automatic:
        _run_description(api, settings, route, pull, language, heading)
        refreshed = api.get(f"repos/{settings.repository}/pulls/{route.pull_number}")
        _run_review(api, settings, route, refreshed, language)
    elif route.command == "/describe":
        _run_description(api, settings, route, pull, language, heading)
    elif route.command == "/review":
        _run_review(api, settings, route, pull, language)
    elif route.command == "/ask":
        run_upstream("ask", settings, settings.ask, language)
    else:
        run_upstream(route.command.removeprefix("/"), settings, settings.passthrough, language)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Publish PR-Agent analysis as native GitHub Reviews.")
    command.add_argument("--version", action="version", version=__version__)
    return command


def cli() -> None:
    """Validate CLI flags and execute the GitHub Actions event."""
    parser().parse_args()
    run(Settings.from_environment())


if __name__ == "__main__":
    cli()
