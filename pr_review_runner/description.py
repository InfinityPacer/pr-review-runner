"""PR description marker ownership and response-language selection."""

from __future__ import annotations

import re

START_MARKER = "<!-- pr-agent-summary:start -->"
END_MARKER = "<!-- pr-agent-summary:end -->"
PLACEHOLDER = f"{START_MARKER}\npr_agent:summary\n{END_MARKER}"
OWNED_BLOCK = re.compile(
    r"(?ims)^##\s+(?:PR-Agent\s+摘要|PR-Agent\s+Summary)\s*\n\s*"
    r"<!-- pr-agent-summary:start -->.*?<!-- pr-agent-summary:end -->\s*"
)
UNFILLED_BLOCK = re.compile(
    r"(?ims)^##\s+(?:PR-Agent\s+摘要|PR-Agent\s+Summary)\s*\n\s*"
    r"<!-- pr-agent-summary:start -->\s*pr_agent:summary\s*<!-- pr-agent-summary:end -->\s*"
)


def response_language(pull: dict) -> tuple[str, str]:
    """Select Chinese for CJK or sparse titles, otherwise English."""
    title = str(pull.get("title") or "")
    body = re.sub(
        r"<!-- pr-agent-summary:start -->.*?<!-- pr-agent-summary:end -->",
        " ",
        str(pull.get("body") or ""),
        flags=re.DOTALL,
    )
    text = f"{title}\n{body}"
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"\b[A-Za-z][A-Za-z]{2,}\b", text))
    return ("zh-CN", "PR-Agent 摘要") if cjk_count >= 4 or latin_words < 8 else ("en-US", "PR-Agent Summary")


def prepare_body(body: str, heading: str, changed_files: int) -> str:
    """Insert only the marker block owned by the description command."""
    block = f"## {heading}\n\n{PLACEHOLDER}"
    start_index = body.find(START_MARKER)
    end_index = body.find(END_MARKER, start_index + len(START_MARKER)) if start_index >= 0 else -1
    if changed_files == 0:
        return OWNED_BLOCK.sub("", body).rstrip() if OWNED_BLOCK.search(body) else body
    if start_index >= 0 and end_index >= 0:
        normalized = re.sub(
            r"(?im)^##\s+(PR-Agent\s+摘要|PR-Agent\s+Summary)\s*\n\s*(?=<!-- pr-agent-summary:start -->)",
            f"## {heading}\n\n",
            body,
        )
        start_index = normalized.find(START_MARKER)
        end_index = normalized.find(END_MARKER, start_index + len(START_MARKER))
        return normalized[:start_index] + PLACEHOLDER + normalized[end_index + len(END_MARKER) :]
    if start_index >= 0 or END_MARKER in body:
        return body
    return f"{body.rstrip()}\n\n{block}\n" if body.strip() else f"{block}\n"


def remove_unfilled_body(body: str) -> str:
    """Remove a placeholder left behind when description generation fails."""
    return UNFILLED_BLOCK.sub("", body).rstrip() if PLACEHOLDER in body else body
