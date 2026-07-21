"""Generate a PR description Summary without publishing the pull-request body."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

_SUMMARY_PLACEHOLDER = "pr_agent:summary"


def _pull_url(event: dict) -> str:
    """Resolve the pull-request API URL from supported GitHub event payloads."""
    pull_request = event.get("pull_request") or (event.get("issue") or {}).get("pull_request") or {}
    url = str(pull_request.get("url") or "")
    if not url:
        raise ValueError("GitHub event does not contain a pull-request URL")
    return url


def _write_summary_output(path: Path, summary: str) -> None:
    """Write the generated Summary using the runner's JSON output contract."""
    with path.open("a", encoding="utf-8") as handle:
        print(f"description={json.dumps({'summary': summary}, ensure_ascii=False)}", file=handle)


async def _generate(pr_url: str) -> str:
    """Run the pinned PR-Agent describe tool against an in-memory marker."""
    from pr_agent.config_loader import get_settings
    from pr_agent.git_providers.utils import apply_repo_settings
    from pr_agent.tools.pr_description import PRDescription

    settings = get_settings()
    settings.set("GITHUB.USER_TOKEN", os.environ["GITHUB_TOKEN"])
    settings.set("GITHUB.DEPLOYMENT_TYPE", "user")
    apply_repo_settings(pr_url)
    settings.set("CONFIG.PUBLISH_OUTPUT", False)

    description = PRDescription(pr_url)
    # The provider snapshot remains in vars for model context; only rendering uses this private marker.
    description.user_description = _SUMMARY_PLACEHOLDER
    await description.run()
    data = getattr(settings, "data", None)
    summary = data.get("artifact") if isinstance(data, dict) else None
    if not isinstance(summary, str) or not summary.strip() or summary.strip() == _SUMMARY_PLACEHOLDER:
        raise RuntimeError("PR-Agent describe produced no Summary")
    return summary.strip()


def main() -> None:
    """Generate one Summary and expose it to the parent runner process."""
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    with event_path.open(encoding="utf-8") as handle:
        event = json.load(handle)
    if not isinstance(event, dict):
        raise ValueError("GITHUB_EVENT_PATH must contain a JSON object")
    summary = asyncio.run(_generate(_pull_url(event)))
    _write_summary_output(Path(os.environ["GITHUB_OUTPUT"]), summary)


if __name__ == "__main__":
    main()
