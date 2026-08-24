from pathlib import Path


def test_release_build_pushes_by_digest_without_candidate_tag() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = workflow.split("  publish-release:", 1)[1]

    assert (
        "outputs: type=image,name=ghcr.io/infinitypacer/pr-review-runner,"
        "push-by-digest=true,name-canonical=true,push=true"
    ) in release
    assert "sha-${{ github.sha }}" not in release
    assert '"ghcr.io/infinitypacer/pr-review-runner@${SOURCE_DIGEST}"' in release
    assert "--tag ghcr.io/infinitypacer/pr-review-runner:edge" in release
    assert '--tag "ghcr.io/infinitypacer/pr-review-runner:${VERSION}"' in release
    assert "--tag ghcr.io/infinitypacer/pr-review-runner:latest" in release
