# Design

## Boundary

The source repository owns GitHub event routing, PR policy, model-route defaults, description-marker ownership, structured Review rendering, and image publication. PR-Agent owns diff analysis, description generation, and question answering.

The runtime never checks out or executes pull request code. `pull_request_target` supplies base-repository secrets, so all PR content is treated as untrusted data and is read only through the GitHub API.

## Runtime Flow

1. Validate the GitHub event, sender, manual role, slash command, and configured command denylist.
2. Read the current PR and apply label, title, and automatic-scope policies.
3. Run each PR-Agent command in a fresh subprocess so model and publishing settings cannot leak between routes. Commands without runner-owned output handling pass through to PR-Agent.
4. For Review, disable upstream publication and capture its structured result.
5. Recheck the head SHA, render one native Review, recheck the head again, then publish.
6. Delete only legacy issue comments with explicit runner-owned markers.

## Release Flow

Image publication is manually selected as `edge` or `release` from the CI workflow. Edge mode overwrites the fixed `edge` tag from `main` for external validation. Release mode verifies that the edge image reports the same version as both local package version sources, then promotes its digest to the version tag and `latest` without rebuilding it. A failed validation leaves release tags unchanged.
