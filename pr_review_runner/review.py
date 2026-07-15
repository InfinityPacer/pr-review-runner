"""Render structured PR-Agent findings as one native GitHub Review."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote

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
    for finding in findings:
        if finding["line"] not in changed_lines.get(finding["path"], set()):
            continue
        if finding["fingerprint"] in fingerprints or (finding["path"], finding["line"]) in locations:
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

    short_sha = head_sha[:7]
    commit_url = f"https://github.com/{repository}/commit/{head_sha}"
    chinese = language == "zh-CN"
    lines = [SUMMARY_MARKER, "## PR-Agent Code Review", ""]
    if findings:
        separator = "：" if chinese else ":"
        for finding in findings:
            location = f"{finding['path']}:{finding['line']}"
            path = quote(finding["path"], safe="/")
            code_url = f"https://github.com/{repository}/blob/{head_sha}/{path}#L{finding['line']}"
            concise = " ".join(finding["content"].split())[:360]
            badge = priority_badge(finding["priority"])
            badge_prefix = f"{badge} " if badge else ""
            lines.append(f"- {badge_prefix}[{location}]({code_url}){separator} **{finding['header']}** - {concise}")
    elif chinese:
        lines.append("本次变更无需提出审查意见，暂无其他反馈。")
    else:
        lines.append("There are no review comments for the current changes. I have no additional feedback to provide.")
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
