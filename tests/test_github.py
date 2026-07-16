import pytest

from pr_review_runner.github import GitHubApi, GitHubApiError


def test_review_thread_resolutions_follow_graphql_pagination(monkeypatch) -> None:
    api = GitHubApi("token")
    cursors: list[str | None] = []
    responses = [
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {"nodes": [{"fullDatabaseId": "101"}]},
                                }
                            ],
                            "pageInfo": {"hasNextPage": True, "endCursor": "next-page"},
                        }
                    }
                }
            }
        },
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": True,
                                    "comments": {"nodes": [{"fullDatabaseId": "202"}]},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        },
    ]

    def fake_post(endpoint: str, payload: dict) -> dict:
        assert endpoint == "graphql"
        assert payload["variables"]["owner"] == "owner"
        assert payload["variables"]["name"] == "repo"
        assert payload["variables"]["number"] == 7
        cursors.append(payload["variables"]["cursor"])
        return responses.pop(0)

    monkeypatch.setattr(api, "post", fake_post)

    assert api.review_thread_resolutions("owner/repo", 7) == {101: False, 202: True}
    assert cursors == [None, "next-page"]


def test_review_thread_resolutions_reject_graphql_errors(monkeypatch) -> None:
    api = GitHubApi("token")
    monkeypatch.setattr(api, "post", lambda *_: {"errors": [{"message": "denied"}]})

    with pytest.raises(GitHubApiError, match="denied"):
        api.review_thread_resolutions("owner/repo", 7)
