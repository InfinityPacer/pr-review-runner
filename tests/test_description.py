from pr_review_runner.description import (
    END_MARKER,
    PLACEHOLDER,
    START_MARKER,
    prepare_body,
    remove_unfilled_body,
    response_language,
)


def test_response_language_ignores_owned_summary() -> None:
    chinese = {"title": "修复审查输出", "body": ""}
    english = {
        "title": "Publish structured pull request reviews",
        "body": (
            "This change keeps contributor text and updates native review output.\n"
            f"{START_MARKER}\n中文摘要内容\n{END_MARKER}"
        ),
    }

    assert response_language(chinese) == ("zh-CN", "PR-Agent 摘要")
    assert response_language(english) == ("en-US", "PR-Agent Summary")


def test_prepare_and_cleanup_preserve_contributor_body() -> None:
    body = "Contributor context."
    prepared = prepare_body(body, "PR-Agent Summary", 1)

    assert prepared.startswith(body)
    assert PLACEHOLDER in prepared
    assert remove_unfilled_body(prepared) == body


def test_prepare_fails_safe_for_incomplete_markers() -> None:
    body = f"Contributor context.\n\n{START_MARKER}\npartial"
    assert prepare_body(body, "PR-Agent Summary", 1) == body


def test_zero_file_pr_removes_only_owned_block() -> None:
    body = f"Contributor context.\n\n## PR-Agent Summary\n\n{PLACEHOLDER}\n"
    assert prepare_body(body, "PR-Agent Summary", 0) == "Contributor context."
