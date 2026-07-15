from pr_review_runner.review import LEGACY_SUMMARY_MARKERS, legacy_summary_comment_ids, render_review_payload

HEAD_SHA = "abcdef1234567890"


def files() -> list[dict]:
    return [
        {
            "filename": "fixtures/review_target.py",
            "patch": "@@ -1,2 +1,3 @@\n keep\n+bad = True\n end",
        }
    ]


def finding(level: str = "HIGH") -> dict:
    return {
        "key_issues_to_review": [
            {
                "relevant_file": "fixtures/review_target.py",
                "start_line": 2,
                "issue_header": f"[{level}] Contract regression",
                "issue_content": "The added behavior violates the declared contract.",
            }
        ],
    }


def render(
    review: dict,
    comments: list[dict] | None = None,
    reviews: list[dict] | None = None,
    language: str = "zh-CN",
) -> dict | None:
    return render_review_payload(review, files(), comments or [], reviews or [], "owner/repo", HEAD_SHA, language)


def test_priority_badges_render_in_summary_and_inline_comment() -> None:
    badge_urls = {
        "HIGH": "high-priority.svg",
        "MEDIUM": "medium-priority.svg",
        "LOW": "low-priority.svg",
    }
    for level, suffix in badge_urls.items():
        payload = render(finding(level))
        assert payload is not None
        assert suffix in payload["body"]
        assert suffix in payload["comments"][0]["body"]
        assert f"[{level}]" not in payload["body"]
        assert f"[{level}]" not in payload["comments"][0]["body"]


def test_unclassified_finding_remains_visible_without_badge() -> None:
    review = finding()
    review["key_issues_to_review"][0]["issue_header"] = "Contract regression"
    payload = render(review)

    assert payload is not None
    assert "Contract regression" in payload["body"]
    assert "priority.svg" not in payload["body"]


def test_no_feedback_uses_natural_localized_summary() -> None:
    chinese = render({})
    english = render({}, language="en-US")

    assert chinese is not None and "本次变更无需提出审查意见，暂无其他反馈。" in chinese["body"]
    assert english is not None and "There are no review comments for the current changes." in english["body"]
    assert "comments" not in chinese


def test_existing_location_deduplicates_inline_comment_but_keeps_summary() -> None:
    first = render(finding())
    assert first is not None
    existing = {
        "user": {"login": "github-actions[bot]"},
        "path": "fixtures/review_target.py",
        "line": 2,
        "body": first["comments"][0]["body"],
    }
    second = render(finding(), comments=[existing])

    assert second is not None
    assert "comments" not in second
    assert "Contract regression" in second["body"]


def test_identical_same_head_review_is_not_republished() -> None:
    first = render({})
    assert first is not None
    existing = {"user": {"login": "github-actions[bot]"}, "commit_id": HEAD_SHA, "body": first["body"]}
    assert render({}, reviews=[existing]) is None


def test_legacy_cleanup_never_selects_normal_discussion() -> None:
    comments = [
        {"id": index + 1, "user": {"login": "github-actions[bot]"}, "body": f"{marker}\nold"}
        for index, marker in enumerate(LEGACY_SUMMARY_MARKERS)
    ]
    comments.extend(
        [
            {"id": 9, "user": {"login": "github-actions[bot]"}, "body": "normal automation discussion"},
            {"id": 10, "user": {"login": "maintainer"}, "body": f"{LEGACY_SUMMARY_MARKERS[0]}\nquoted"},
        ]
    )

    assert legacy_summary_comment_ids(comments) == [1, 2, 3]
