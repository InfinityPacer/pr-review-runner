import json

from pr_review_runner.discussion import build_review_discussion


def test_discussion_keeps_human_comments_and_review_thread_context() -> None:
    issue_comments = [
        {
            "id": 1,
            "user": {"login": "maintainer", "type": "User"},
            "body": "requirements.txt already includes requirements.in.",
            "created_at": "2026-07-16T08:00:00Z",
        },
        {
            "id": 2,
            "user": {"login": "maintainer", "type": "User"},
            "body": "<!-- edited command -->\n/review",
            "created_at": "2026-07-16T08:01:00Z",
        },
        {
            "id": 3,
            "user": {"login": "dependabot[bot]", "type": "Bot"},
            "body": "Automated dependency status.",
            "created_at": "2026-07-16T08:02:00Z",
        },
    ]
    review_comments = [
        {
            "id": 10,
            "user": {"login": "github-actions[bot]", "type": "Bot"},
            "body": "<!-- pr-agent-review:abc -->\nThe provider authentication path is incomplete.",
            "path": "app/provider.py",
            "line": 20,
            "created_at": "2026-07-16T08:03:00Z",
        },
        {
            "id": 11,
            "in_reply_to_id": 10,
            "user": {"login": "contributor", "type": "User"},
            "body": "This is now handled by resolve_provider_auth().",
            "path": "app/provider.py",
            "line": 20,
            "created_at": "2026-07-16T08:04:00Z",
        },
        {
            "id": 20,
            "user": {"login": "unrelated[bot]", "type": "Bot"},
            "body": "Unrelated automation output.",
            "path": "app/other.py",
            "line": 5,
            "created_at": "2026-07-16T08:05:00Z",
        },
        {
            "id": 30,
            "user": {"login": "reviewer", "type": "User"},
            "body": "Please preserve the fallback ordering contract.",
            "path": "app/models.py",
            "line": 8,
            "created_at": "2026-07-16T08:06:00Z",
        },
    ]

    context = build_review_discussion(issue_comments, review_comments)
    payload = json.loads(context)

    assert payload["issue_comments"] == [
        {"author": "maintainer", "body": "requirements.txt already includes requirements.in."}
    ]
    assert len(payload["review_threads"]) == 2
    provider_thread = next(thread for thread in payload["review_threads"] if thread["path"] == "app/provider.py")
    assert [comment["author"] for comment in provider_thread["comments"]] == [
        "github-actions[bot]",
        "contributor",
    ]
    assert "pr-agent-review" not in provider_thread["comments"][0]["body"]
    assert "resolve_provider_auth" in provider_thread["comments"][1]["body"]
    assert "/review" not in context
    assert "dependabot" not in context
    assert "Unrelated automation output" not in context


def test_discussion_is_bounded_and_prefers_recent_context() -> None:
    issue_comments = [
        {
            "id": index,
            "user": {"login": f"user-{index}", "type": "User"},
            "body": f"comment-{index}-" + ("x" * 120),
            "created_at": f"2026-07-16T08:0{index}:00Z",
        }
        for index in range(1, 6)
    ]

    context = build_review_discussion(issue_comments, [], max_chars=420)

    assert len(context) <= 420
    assert "comment-5" in context
    assert "comment-1" not in context
    assert json.loads(context)["truncated"] is True


def test_empty_discussion_does_not_add_prompt_payload() -> None:
    assert build_review_discussion([], []) == ""
