import pytest

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
    labels = {"HIGH": "高风险", "MEDIUM": "中风险", "LOW": "低风险"}
    return {
        "review_summary": f"本次审查发现一个{labels[level]}问题，缓存删除行为可能造成无关数据丢失。",
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
    resolved_comment_ids: set[int] | None = None,
) -> dict | None:
    return render_review_payload(
        review,
        files(),
        comments or [],
        reviews or [],
        "owner/repo",
        HEAD_SHA,
        language,
        resolved_comment_ids or set(),
    )


def test_priority_badges_render_only_in_inline_comment() -> None:
    badge_urls = {
        "HIGH": "high-priority.svg",
        "MEDIUM": "medium-priority.svg",
        "LOW": "low-priority.svg",
    }
    for level, suffix in badge_urls.items():
        payload = render(finding(level))
        assert payload is not None
        assert suffix not in payload["body"]
        assert suffix in payload["comments"][0]["body"]
        assert "本次审查发现一个" in payload["body"]
        assert "The added behavior violates the declared contract." not in payload["body"]
        assert f"[{level}]" not in payload["body"]
        assert f"[{level}]" not in payload["comments"][0]["body"]


def test_unclassified_finding_remains_visible_without_badge() -> None:
    review = finding()
    review["key_issues_to_review"][0]["issue_header"] = "Contract regression"
    review["review_summary"] = "本次审查发现一个合同回归问题，需要在合入前处理。"
    payload = render(review)

    assert payload is not None
    assert "Contract regression" in payload["comments"][0]["body"]
    assert "priority.svg" not in payload["body"]
    assert "priority.svg" not in payload["comments"][0]["body"]


def test_no_feedback_uses_natural_localized_summary() -> None:
    chinese = render(
        {"review_summary": "本次变更新增缓存键查询帮助函数，并保持现有缓存语义不变，暂未发现需要提出的审查意见。"}
    )
    english = render(
        {
            "review_summary": (
                "This change adds a cache-key lookup helper while preserving existing cache semantics. "
                "There are no review comments to provide."
            )
        },
        language="en-US",
    )

    assert chinese is not None
    assert "本次变更新增缓存键查询帮助函数" in chinese["body"]
    assert "暂未发现需要提出的审查意见" in chinese["body"]
    assert english is not None
    assert "This change adds a cache-key lookup helper" in english["body"]
    assert "There are no review comments to provide." in english["body"]
    assert "comments" not in chinese


def test_no_feedback_fallback_is_explicit_without_inventing_a_change_summary() -> None:
    payload = render({})

    assert payload is not None
    assert "已完成本次代码审查，暂未发现需要提出的审查意见。" in payload["body"]


def test_existing_location_deduplicates_inline_comment_but_keeps_summary() -> None:
    first = render(finding())
    assert first is not None
    existing = {
        "id": 101,
        "user": {"login": "github-actions[bot]"},
        "path": "fixtures/review_target.py",
        "line": 2,
        "body": first["comments"][0]["body"],
        "html_url": "https://github.com/owner/repo/pull/7#discussion_r101",
    }
    second = render(finding(), comments=[existing])

    assert second is not None
    assert "comments" not in second
    assert "本次审查发现一个高风险问题" in second["body"]
    assert "https://github.com/owner/repo/pull/7#discussion_r101" in second["body"]
    assert "The added behavior violates the declared contract." not in second["body"]


def test_resolved_thread_does_not_suppress_a_new_inline_comment() -> None:
    first = render(finding())
    assert first is not None
    existing = {
        "id": 101,
        "user": {"login": "github-actions[bot]"},
        "path": "fixtures/review_target.py",
        "line": 2,
        "body": first["comments"][0]["body"],
        "html_url": "https://github.com/owner/repo/pull/7#discussion_r101",
    }

    second = render(finding(), comments=[existing], resolved_comment_ids={101})

    assert second is not None
    assert len(second["comments"]) == 1
    assert "discussion_r101" not in second["body"]


def test_missing_model_summary_falls_back_without_copying_inline_content() -> None:
    review = finding()
    review.pop("review_summary")

    payload = render(review)

    assert payload is not None
    assert "已完成本次代码审查，发现的问题及处理建议见行内评论。" in payload["body"]
    assert "The added behavior violates the declared contract." not in payload["body"]


def test_missing_summary_does_not_claim_an_inline_comment_when_location_is_invalid() -> None:
    review = finding()
    review.pop("review_summary")
    review["key_issues_to_review"][0]["start_line"] = 99

    payload = render(review)

    assert payload is not None
    assert "识别到的问题无法定位到可评论的变更行" in payload["body"]
    assert "comments" not in payload


def test_missing_summary_fails_instead_of_using_the_wrong_configured_locale() -> None:
    with pytest.raises(RuntimeError, match="configured locale ja-JP"):
        render({}, language="ja-JP")


def test_same_payload_deduplicates_multiple_findings_at_one_location() -> None:
    review = finding()
    duplicate = dict(review["key_issues_to_review"][0])
    duplicate["issue_header"] = "[MEDIUM] Secondary interpretation"
    duplicate["issue_content"] = "The same line has another interpretation."
    review["key_issues_to_review"].append(duplicate)

    payload = render(review)

    assert payload is not None
    assert len(payload["comments"]) == 1


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
