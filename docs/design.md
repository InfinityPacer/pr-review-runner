# Design

## Boundary

The source repository owns GitHub event routing, PR policy, model-route defaults, description-marker ownership, structured Review rendering, and image publication. PR-Agent owns model-provider configuration, diff analysis, description generation, and question answering. Provider environment variables pass through unchanged under their PR-Agent-native names.

The runtime never checks out or executes pull request code. `pull_request_target` supplies base-repository secrets, so all PR content is treated as untrusted data and is read only through the GitHub API.

## Runtime Flow

1. Validate the GitHub event, sender, manual role, slash command, configured command denylist, and bundled PR-Agent command registry.
2. Read the current PR and apply label, title, and automatic-scope policies.
3. For Review, read a bounded selection of human pull-request discussion and pass it to the model as untrusted evidence that must be checked against the current code.
4. Run each PR-Agent command in a fresh subprocess so model and publishing settings cannot leak between routes. Commands without runner-owned output handling pass through to PR-Agent.
5. For Review, disable upstream publication and capture its structured result.
6. Recheck the head SHA, render one native Review, recheck the head again, then publish. Unresolved thread roots suppress duplicate inline comments and produce links in the summary; resolved roots do not suppress new findings.
7. Delete only legacy issue comments with explicit runner-owned markers.

## Release Flow

Image publication is manually selected as `edge` or `release` from the CI workflow. Edge mode overwrites the fixed `edge` tag from `main` for external validation. Release mode verifies that the edge image reports the same version as both local package version sources, then promotes its digest to the version tag and `latest` without rebuilding it. A failed validation leaves release tags unchanged.
