from pathlib import Path

from pr_review_runner.config import ModelRoute, Settings
from pr_review_runner.events import route_event, should_skip_pull


def settings(
    event_name: str = "issue_comment",
    scope: str = "all",
    disabled_commands: tuple[str, ...] = (),
) -> Settings:
    route = ModelRoute("model", "high")
    return Settings(
        repository="owner/repo",
        event_name=event_name,
        event_path=Path("event.json"),
        github_token="token",
        openai_key="key",
        openai_api_base="https://example.test/v1",
        describe=route,
        automatic_review=route,
        manual_review=route,
        ask=route,
        passthrough=route,
        fallback_models=("fallback",),
        custom_model_max_tokens=100,
        ai_timeout=60,
        auto_review_scope=scope,
        allowed_associations=("OWNER", "CONTRIBUTOR"),
        disabled_commands=disabled_commands,
        skip_label="skip pr-agent",
        skip_title_pattern=r"^(?:\[Auto\]|Auto)",
        max_findings=4,
    )


def comment_event(body: str = "/review", association: str = "OWNER", action: str = "created") -> dict:
    return {
        "action": action,
        "sender": {"type": "User"},
        "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
        "comment": {"body": body, "author_association": association},
    }


def pull(head_repo: str = "fork/repo", title: str = "Feature", labels: list[dict] | None = None) -> dict:
    return {"title": title, "labels": labels or [], "head": {"repo": {"full_name": head_repo}}}


def test_manual_routes_allow_created_and_edited_commands() -> None:
    assert route_event(comment_event("/describe"), settings()).command == "/describe"
    assert route_event(comment_event("/review focus", action="edited"), settings()).command == "/review"
    assert route_event(comment_event("/ask why"), settings()).command == "/ask"
    assert route_event(comment_event("/improve --extended"), settings()).command == "/improve"
    assert route_event(comment_event("/update_changelog"), settings()).command == "/update_changelog"


def test_manual_routes_reject_unknown_roles_bots_and_disabled_commands() -> None:
    assert route_event(comment_event(association="NONE"), settings()) is None
    bot = comment_event()
    bot["sender"]["type"] = "Bot"
    assert route_event(bot, settings()) is None
    current = settings(disabled_commands=("/improve",))
    assert route_event(comment_event("/IMPROVE --extended"), current) is None
    assert route_event(comment_event("please /review"), settings()) is None


def test_automatic_scope_can_limit_reviews_to_forks() -> None:
    event = {"action": "opened", "sender": {"type": "User"}, "pull_request": {"number": 7}}
    route = route_event(event, settings("pull_request_target", "forks"))

    assert route is not None and route.automatic
    assert not should_skip_pull(pull("contributor/fork"), settings("pull_request_target", "forks"), route)
    assert should_skip_pull(pull("owner/repo"), settings("pull_request_target", "forks"), route)


def test_skip_rules_apply_to_automatic_and_manual_routes() -> None:
    route = route_event(comment_event(), settings())
    assert route is not None
    assert should_skip_pull(pull(labels=[{"name": "skip pr-agent"}]), settings(), route)
    assert should_skip_pull(pull(title="[Auto] dependency update"), settings(), route)
    assert should_skip_pull(pull(title="Auto dependency update"), settings(), route)
    assert not should_skip_pull(pull(title="Manual feature"), settings(), route)
