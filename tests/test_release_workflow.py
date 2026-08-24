from pathlib import Path


def test_release_build_pushes_by_digest_without_candidate_tag() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = workflow.split("  publish-release:", 1)[1]

    assert (
        "outputs: type=image,name=ghcr.io/infinitypacer/pr-review-runner,"
        "push-by-digest=true,name-canonical=true,push=true"
    ) in release
    assert "sha-${{ github.sha }}" not in release
    assert "provenance: false" in release
    assert '"ghcr.io/infinitypacer/pr-review-runner@${SOURCE_DIGEST}"' in release
    assert "--prefer-index=false" in release
    assert "--tag ghcr.io/infinitypacer/pr-review-runner:edge" in release
    assert '--tag "ghcr.io/infinitypacer/pr-review-runner:${VERSION}"' in release
    assert "--tag ghcr.io/infinitypacer/pr-review-runner:latest" in release


def test_registry_provenance_is_not_published() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert workflow.count("provenance: false") == 2
    assert "actions/attest-build-provenance" not in workflow
    assert "push-to-registry" not in workflow
    assert "attestations: write" not in workflow
    assert "id-token: write" not in workflow
