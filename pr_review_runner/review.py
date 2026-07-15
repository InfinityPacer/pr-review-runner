"""Render structured PR-Agent findings as one native GitHub Review."""

from __future__ import annotations

import hashlib
import re

PRIORITY_BADGES = {
    "high": "https://www.gstatic.com/codereviewagent/high-priority.svg",
    "medium": "https://www.gstatic.com/codereviewagent/medium-priority.svg",
    "low": "https://www.gstatic.com/codereviewagent/low-priority.svg",
}
PRIORITY_PATTERN = re.compile(r"^\[(HIGH|MEDIUM|LOW)\]\s*(.+)$", re.IGNORECASE | re.DOTALL)
COMMENT_MARKER_PATTERN = re.compile(r"<!-- pr-agent-review:([0-9a-f]{16}) -->")
HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
SUMMARY_MARKER = "<!-- pr-agent-review-summary -->"
LEGACY_SUMMARY_MARKERS = (
    SUMMARY_MARKER,
    "<!-- pr-agent-code-review-summary -->",
    "<!-- pr-agent-lab:review -->",
)


def changed_lines_by_file(files: list[dict]) -> dict[str, set[int]]:
    """Return right-side added lines eligible for GitHub inline comments."""
    changed_lines: dict[str, set[int]] = {}
    for file_data in files:
        path = str(file_data.get("filename") or "")
        line: int | None = None
        lines: set[int] = set()
        for patch_line in str(file_data.get("patch") or "").splitlines():
            hunk = HUNK_PATTERN.match(patch_line)
            if hunk:
                line = int(hunk.group(1))
                continue
            if line is None or patch_line.startswith("\\"):
                continue
            if patch_line.startswith("+") and not patch_line.startswith("+++"):
                lines.add(line)
                line += 1
            elif patch_line.startswith("-") and not patch_line.startswith("---"):
                continue
            else:
                line += 1
        changed_lines[path] = lines
    return changed_lines


def split_priority(header: str) -> tuple[str, str]:
    """Remove the internal severity token while preserving unclassified findings."""
    match = PRIORITY_PATTERN.match(header)
    return (match.group(1).lower(), match.group(2).strip()) if match else ("", header)


def priority_badge(priority: str) -> str:
    """Return priority badge Markdown for a classified finding."""
    url = PRIORITY_BADGES.get(priority)
    return f"![{priority}]({url})" if url else ""


def _fallback_summary(findings: list[dict], language: str, has_visible_inline_comment: bool) -> str:
    """Keep publication useful when the model omits only its summary field."""
    normalized_language = language.lower().replace("_", "-")
    chinese = normalized_language.startswith("zh")
    english = normalized_language.startswith("en")
    if not chinese and not english:
        raise RuntimeError(f"review analysis omitted review_summary for configured locale {language}")
    if findings:
        if has_visible_inline_comment and chinese:
            return "已完成本次代码审查，发现的问题及处理建议见行内评论。"
        if has_visible_inline_comment:
            return "The code review is complete. See the inline comments for the identified issues and recommendations."
        if chinese:
            return "已完成本次代码审查，但识别到的问题无法定位到可评论的变更行。"
        return "The code review is complete, but the identified issues could not be attached to changed lines."
    if chinese:
        return "已完成本次代码审查，暂未发现需要提出的审查意见。"
    return "The code review is complete. There are no review comments to provide."


def _review_summary(review: dict, findings: list[dict], language: str, has_visible_inline_comment: bool) -> str:
    """Prefer the model's overall assessment and retain a deterministic fallback."""
    summary = " ".join(str(review.get("review_summary") or "").split())
    return summary or _fallback_summary(findings, language, has_visible_inline_comment)


def _fingerprint(path: str, line: int) -> str:
    normalized = "\n".join((path, str(line)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _findings(review: dict) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple] = set()
    for issue in review.get("key_issues_to_review") or []:
        if not isinstance(issue, dict):
            continue
        path = str(issue.get("relevant_file") or "").strip()
        priority, header = split_priority(str(issue.get("issue_header") or "").strip())
        content = str(issue.get("issue_content") or "").strip()
        try:
            line = int(issue.get("start_line") or 0)
        except (TypeError, ValueError):
            line = 0
        if not path or not header or not content or line < 1:
            continue
        key = (path, line, header.lower(), " ".join(content.split()).lower())
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "path": path,
                "line": line,
                "priority": priority,
                "header": header,
                "content": content,
                "fingerprint": _fingerprint(path, line),
            }
        )
    return findings


def render_review_payload(
    review: dict,
    files: list[dict],
    comments: list[dict],
    reviews: list[dict],
    repository: str,
    head_sha: str,
    language: str,
) -> dict | None:
    """Build a summary plus deduplicated inline comments for one head SHA."""
    changed_lines = changed_lines_by_file(files)
    fingerprints: set[str] = set()
    locations: set[tuple[str, int]] = set()
    for comment in comments:
        if comment.get("user", {}).get("login") != "github-actions[bot]" or comment.get("line") is None:
            continue
        match = COMMENT_MARKER_PATTERN.search(str(comment.get("body") or ""))
        if not match:
            continue
        fingerprints.add(match.group(1))
        path = str(comment.get("path") or "")
        try:
            line = int(comment.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        if path and line > 0:
            locations.add((path, line))

    findings = _findings(review)
    new_comments: list[dict] = []
    visible_finding_locations: set[tuple[str, int]] = set()
    for finding in findings:
        if finding["line"] not in changed_lines.get(finding["path"], set()):
            continue
        location = (finding["path"], finding["line"])
        if finding["fingerprint"] in fingerprints or location in locations:
            visible_finding_locations.add(location)
            continue
        body = [f"<!-- pr-agent-review:{finding['fingerprint']} -->"]
        badge = priority_badge(finding["priority"])
        if badge:
            body.extend([badge, ""])
        body.extend([f"**{finding['header']}**", "", finding["content"]])
        new_comments.append(
            {
                "path": finding["path"],
                "line": finding["line"],
                "side": "RIGHT",
                "body": "\n".join(body),
            }
        )
        locations.add(location)
        visible_finding_locations.add(location)

    short_sha = head_sha[:7]
    commit_url = f"https://github.com/{repository}/commit/{head_sha}"
    chinese = language.lower().replace("_", "-").startswith("zh")
    lines = [SUMMARY_MARKER, "## PR-Agent Code Review", ""]
    lines.append(_review_summary(review, findings, language, bool(visible_finding_locations)))
    lines.extend(
        [
            "",
            f"审查提交：[{short_sha}]({commit_url})" if chinese else f"Reviewed commit: [{short_sha}]({commit_url})",
            "",
        ]
    )
    payload: dict = {
        "body": "\n".join(lines),
        "commit_id": head_sha,
        "event": "COMMENT",
    }
    if new_comments:
        payload["comments"] = new_comments
    if not new_comments and any(
        existing.get("user", {}).get("login") == "github-actions[bot]"
        and existing.get("commit_id") == head_sha
        and str(existing.get("body") or "") == payload["body"]
        for existing in reviews
    ):
        return None
    return payload


def legacy_summary_comment_ids(comments: list[dict]) -> list[int]:
    """Select only issue comments explicitly owned by historical runner versions."""
    return [
        int(comment["id"])
        for comment in comments
        if comment.get("user", {}).get("login") == "github-actions[bot]"
        and any(str(comment.get("body") or "").startswith(marker) for marker in LEGACY_SUMMARY_MARKERS)
    ]
