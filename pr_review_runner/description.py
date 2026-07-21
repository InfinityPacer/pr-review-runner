"""PR description marker ownership and response-language selection."""

from __future__ import annotations

import re

START_MARKER = "<!-- pr-agent-summary:start -->"
END_MARKER = "<!-- pr-agent-summary:end -->"
OWNED_BLOCK = re.compile(
    r"(?ims)^##\s+(?:PR-Agent\s+摘要|PR-Agent\s+Summary)\s*\n\s*"
    r"<!-- pr-agent-summary:start -->.*?<!-- pr-agent-summary:end -->\s*"
)


def response_language(pull: dict, configured: str = "") -> tuple[str, str]:
    """Honor an explicit locale or infer Chinese and English from contributor text."""
    configured = configured.strip()
    if configured:
        heading = "PR-Agent 摘要" if configured.lower().replace("_", "-").startswith("zh") else "PR-Agent Summary"
        return configured, heading

    title = str(pull.get("title") or "")
    body = re.sub(
        r"<!-- pr-agent-summary:start -->.*?<!-- pr-agent-summary:end -->",
        " ",
        str(pull.get("body") or ""),
        flags=re.DOTALL,
    )
    text = f"{title}\n{body}"
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    has_japanese_or_korean = bool(re.search(r"[\u3040-\u30ff\uac00-\ud7af]", text))
    if cjk_count >= 4 and not has_japanese_or_korean:
        return "zh-CN", "PR-Agent 摘要"
    return "en-US", "PR-Agent Summary"


def update_summary(body: str, heading: str, summary: str) -> str:
    """Replace only the complete Summary block owned by the runner."""
    if START_MARKER in summary or END_MARKER in summary:
        raise ValueError("generated Summary must not contain runner ownership markers")
    block = f"## {heading}\n\n{START_MARKER}\n{summary.strip()}\n{END_MARKER}"
    if OWNED_BLOCK.search(body):
        return OWNED_BLOCK.sub(lambda _: f"{block}\n", body).rstrip() + "\n"
    if START_MARKER in body or END_MARKER in body:
        return body
    return f"{body.rstrip()}\n\n{block}\n" if body.strip() else f"{block}\n"


def remove_summary(body: str) -> str:
    """Remove only a complete Summary block owned by the runner."""
    return OWNED_BLOCK.sub("", body).rstrip() if OWNED_BLOCK.search(body) else body
