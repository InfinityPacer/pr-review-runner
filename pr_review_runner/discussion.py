"""Select bounded pull-request discussion as untrusted review evidence."""

from __future__ import annotations

import json
import re
from collections import defaultdict

DEFAULT_DISCUSSION_MAX_CHARS = 12_000
MAX_COMMENT_BODY_CHARS = 2_000
MAX_REVIEW_THREAD_COMMENTS = 4
COMMAND_PATTERN = re.compile(r"^/[a-z0-9_-]+(?=$|\s)", re.IGNORECASE)
HIDDEN_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)


def _integer(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _author(comment: dict) -> str:
    return str((comment.get("user") or {}).get("login") or "unknown")


def _is_human(comment: dict) -> bool:
    user = comment.get("user") or {}
    login = str(user.get("login") or "")
    return str(user.get("type") or "").lower() != "bot" and not login.lower().endswith("[bot]")


def _clean_body(comment: dict) -> tuple[str, bool]:
    raw = str(comment.get("body") or "").strip()
    if not raw:
        return "", False
    cleaned = HIDDEN_COMMENT_PATTERN.sub("", raw).strip()
    if not cleaned or COMMAND_PATTERN.match(cleaned):
        return "", False
    if len(cleaned) <= MAX_COMMENT_BODY_CHARS:
        return cleaned, False
    return f"{cleaned[: MAX_COMMENT_BODY_CHARS - 16].rstrip()}\n[truncated]", True


def _order(comment: dict) -> tuple[str, int]:
    return str(comment.get("created_at") or ""), _integer(comment.get("id")) or 0


def _review_thread_groups(review_comments: list[dict]) -> list[list[dict]]:
    comments_by_id = {
        comment_id: comment for comment in review_comments if (comment_id := _integer(comment.get("id"))) is not None
    }

    def root_id(comment: dict) -> int:
        comment_id = _integer(comment.get("id")) or -id(comment)
        parent_id = _integer(comment.get("in_reply_to_id"))
        visited: set[int] = set()
        while parent_id and parent_id in comments_by_id and parent_id not in visited:
            visited.add(parent_id)
            comment_id = parent_id
            parent_id = _integer(comments_by_id[parent_id].get("in_reply_to_id"))
        return parent_id or comment_id

    groups: defaultdict[int, list[dict]] = defaultdict(list)
    for comment in review_comments:
        groups[root_id(comment)].append(comment)
    return [sorted(group, key=_order) for group in groups.values()]


def _discussion_units(issue_comments: list[dict], review_comments: list[dict]) -> tuple[list[dict], bool]:
    units: list[dict] = []
    body_truncated = False
    for comment in issue_comments:
        body, shortened = _clean_body(comment)
        if not _is_human(comment) or not body:
            continue
        body_truncated |= shortened
        units.append(
            {
                "kind": "issue_comments",
                "order": _order(comment),
                "payload": {"author": _author(comment), "body": body},
            }
        )

    for group in _review_thread_groups(review_comments):
        human_comments: list[tuple[dict, str]] = []
        for comment in group:
            body, shortened = _clean_body(comment)
            if _is_human(comment) and body:
                human_comments.append((comment, body))
                body_truncated |= shortened
        if not human_comments:
            continue

        root = group[0]
        root_body, root_shortened = _clean_body(root)
        included: list[tuple[dict, str]] = []
        if root_body:
            included.append((root, root_body))
            body_truncated |= root_shortened
        included.extend((comment, body) for comment, body in human_comments if comment is not root)
        if len(included) > MAX_REVIEW_THREAD_COMMENTS:
            root_entry = included[:1] if included[0][0] is root else []
            replies = included[1:] if root_entry else included
            available_replies = MAX_REVIEW_THREAD_COMMENTS - len(root_entry)
            included = root_entry + replies[-available_replies:]
            body_truncated = True

        reference = root if root_body else human_comments[0][0]
        line = _integer(reference.get("line")) or _integer(reference.get("original_line"))
        payload: dict[str, object] = {
            "path": str(reference.get("path") or ""),
            "comments": [
                {
                    "author": _author(comment),
                    "role": "root" if comment is root else "reply",
                    "body": body,
                }
                for comment, body in included
            ],
        }
        if line is not None:
            payload["line"] = line
        units.append(
            {
                "kind": "review_threads",
                "order": max(_order(comment) for comment, _ in human_comments),
                "payload": payload,
            }
        )
    return units, body_truncated


def _encode(units: list[dict], truncated: bool) -> str:
    ordered = sorted(units, key=lambda unit: unit["order"])
    payload = {
        "issue_comments": [unit["payload"] for unit in ordered if unit["kind"] == "issue_comments"],
        "review_threads": [unit["payload"] for unit in ordered if unit["kind"] == "review_threads"],
        "truncated": truncated,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_review_discussion(
    issue_comments: list[dict],
    review_comments: list[dict],
    max_chars: int = DEFAULT_DISCUSSION_MAX_CHARS,
) -> str:
    """Return recent human discussion as size-limited JSON for the review prompt."""
    if max_chars < 256:
        raise ValueError("review discussion limit must be at least 256 characters")
    units, body_truncated = _discussion_units(issue_comments, review_comments)
    if not units:
        return ""

    selected: list[dict] = []
    for unit in sorted(units, key=lambda candidate: candidate["order"], reverse=True):
        candidate = selected + [unit]
        if len(_encode(candidate, True)) <= max_chars:
            selected = candidate

    truncated = body_truncated or len(selected) < len(units)
    encoded = _encode(selected, truncated)
    while selected and len(encoded) > max_chars:
        selected.pop()
        truncated = True
        encoded = _encode(selected, truncated)
    return encoded
