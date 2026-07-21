import pytest

from pr_review_runner.description import (
    END_MARKER,
    START_MARKER,
    remove_summary,
    response_language,
    update_summary,
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
    assert response_language({"title": "Fix crash", "body": ""}) == ("en-US", "PR-Agent Summary")


def test_explicit_response_language_overrides_pull_text() -> None:
    pull = {"title": "修复审查输出", "body": "补充中文说明。"}

    assert response_language(pull, "ja-JP") == ("ja-JP", "PR-Agent Summary")
    assert response_language({"title": "Fix crash"}, "zh-TW") == ("zh-TW", "PR-Agent 摘要")


def test_update_and_remove_preserve_contributor_body() -> None:
    body = "Contributor context."
    updated = update_summary(body, "PR-Agent Summary", "Generated summary.")

    assert updated.startswith(body)
    assert "Generated summary." in updated
    assert remove_summary(updated) == body


def test_update_fails_safe_for_incomplete_markers() -> None:
    body = f"Contributor context.\n\n{START_MARKER}\npartial"
    assert update_summary(body, "PR-Agent Summary", "Generated summary.") == body


def test_update_replaces_only_owned_block_and_normalizes_heading() -> None:
    body = f"Contributor context.\n\n## PR-Agent Summary\n\n{START_MARKER}\nOld summary.\n{END_MARKER}\n"

    updated = update_summary(body, "PR-Agent 摘要", "新摘要。")

    assert updated.startswith("Contributor context.")
    assert "## PR-Agent 摘要" in updated
    assert "新摘要。" in updated
    assert "Old summary." not in updated


def test_update_preserves_backslashes_and_rejects_nested_markers() -> None:
    body = f"Contributor context.\n\n## PR-Agent Summary\n\n{START_MARKER}\nOld summary.\n{END_MARKER}\n"

    updated = update_summary(body, "PR-Agent Summary", r"Keep \1 and C:\\workspace literal.")

    assert r"Keep \1 and C:\\workspace literal." in updated
    with pytest.raises(ValueError, match="ownership markers"):
        update_summary(body, "PR-Agent Summary", START_MARKER)
