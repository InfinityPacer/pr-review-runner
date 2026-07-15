# PR Review Runner

PR Review Runner is a containerized GitHub Actions wrapper around [PR-Agent](https://github.com/qodo-ai/pr-agent). It publishes code-review results as a native GitHub Review with a summary, line comments, and priority badges.

The project is independently maintained and is not affiliated with Qodo or GitHub. Thanks to the PR-Agent project and its contributors.

## Usage

Create a workflow such as `.github/workflows/pr-review.yml`:

```yaml
name: PR Review

on:
  pull_request_target:
    types: [opened, reopened, ready_for_review, review_requested, synchronize]
  issue_comment:
    types: [created, edited]

permissions:
  contents: read
  pull-requests: write
  issues: write

jobs:
  review:
    if: >-
      github.event.sender.type != 'Bot' &&
      (
        github.event_name == 'pull_request' ||
        github.event_name == 'pull_request_target' ||
        github.event.issue.pull_request != null
      )
    concurrency:
      group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.event.issue.number }}
      cancel-in-progress: ${{ github.event_name == 'pull_request' || github.event_name == 'pull_request_target' }}
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Run PR Review
        uses: docker://ghcr.io/infinitypacer/pr-review-runner:latest
        env:
          GITHUB_TOKEN: ${{ github.token }}
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          OPENAI.API_BASE: ${{ secrets.OPENAI_API_BASE }}
```

`GITHUB_TOKEN` is the short-lived token created for the workflow run. A personal access token is not required.

The workflow uses `pull_request_target` so base-repository secrets are available. Do not add a checkout step or execute pull-request code in this job. The runner reads pull-request data through the GitHub API.

The runner also accepts `pull_request` when a repository intentionally uses that event. Fork pull requests do not normally receive repository secrets or a write-capable `GITHUB_TOKEN` on `pull_request`, so they cannot usually authenticate the model provider or publish a Review. Choose one pull-request event for automatic processing to avoid duplicate Reviews.

## Provider Configuration

Provider settings pass directly to PR-Agent. Use PR-Agent's native environment variable names for credentials and endpoints.

The workflow example uses `OPENAI_KEY` and an optional `OPENAI.API_BASE`. Other providers can supply their corresponding PR-Agent or LiteLLM variables instead. Override the model routes below when the provider does not expose the default model identifiers.

## Commands

The runner handles these commands directly:

- `/describe` updates a runner-owned summary block in the pull-request body without replacing contributor text.
- `/review` publishes a native `PR-Agent Code Review` summary and eligible line comments.
- `/ask <question>` asks PR-Agent about the pull request.

Equivalent upstream aliases share the same wrapper behavior and command-denylist policy. All remaining commands registered by the bundled PR-Agent, including their arguments, are delegated to PR-Agent. This includes `/improve`, which is enabled by default. Unknown commands are ignored. Refer to the [PR-Agent tool documentation](https://github.com/qodo-ai/pr-agent/tree/main/docs/docs/tools) for delegated command behavior.

Manual commands accept `created` and `edited` comments from `OWNER`, `MEMBER`, `COLLABORATOR`, `CONTRIBUTOR`, and `FIRST_TIME_CONTRIBUTOR` by default. Use `PRR_ALLOWED_ASSOCIATIONS` to replace this list or `PRR_DISABLED_COMMANDS` to disable selected commands.

Pull requests with the `skip pr-agent` label or a title beginning with `[Auto]` or `Auto` are skipped for automatic and manual routes.

## Wrapper Defaults

The wrapper adds independent model routes for the behavior it owns:

| Route | Model | Reasoning effort |
| --- | --- | --- |
| Description | `gpt-5.6-terra` | `medium` |
| Automatic Review | `gpt-5.6-sol` | `xhigh` |
| Manual `/review` | `gpt-5.6-sol` | `xhigh` |
| `/ask` | `gpt-5.6-terra` | `high` |
| Delegated commands | `gpt-5.6-sol` | `xhigh` |

Fallback models are `gpt-5.5` followed by `gpt-5.4`, and the custom model context limit is `1050000`. Route defaults can be replaced with the corresponding `PRR_*_MODEL`, `PRR_*_REASONING_EFFORT`, `PRR_FALLBACK_MODELS`, and `PRR_CUSTOM_MODEL_MAX_TOKENS` variables.

Automatic processing covers all pull requests by default. Set `PRR_AUTO_REVIEW_SCOPE` to `forks` to automate only fork pull requests, or to `manual` to keep only slash commands. Use `PRR_DISABLED_COMMANDS` for a JSON command denylist such as `["/improve"]`.

All other provider and tool configuration follows PR-Agent. Refer to the [upstream documentation](https://github.com/qodo-ai/pr-agent/tree/main/docs/docs) for available settings.

Set PR-Agent's native `config.response_language` environment variable to keep model-generated content from every command in a fixed locale. When it is omitted, the runner selects `zh-CN` for clearly Chinese pull-request titles or descriptions and otherwise uses `en-US`. The programming language of changed files is not used for this decision.

## Review Output

Findings classified as high, medium, or low use visible priority badges on their line comments. The Review body contains a natural-language assessment instead of copying the line comments. When no actionable issue is found, the same assessment summarizes the change and concludes naturally that there is no additional feedback. It does not create a separate issue comment for the review summary.

Analysis is discarded if the pull-request head changes before publication. Identical Reviews and line comments are not published twice for the same head.

## Image Tags

- `edge` tracks the most recently published validation image.
- The package version tag is an immutable release.
- `latest` points to the same image digest as the current version tag.

Image publication is manual. A release promotes the validated `edge` digest to the package version and `latest` without rebuilding it.

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
docker build --tag pr-review-runner:test .
docker run --rm pr-review-runner:test --version
```

## License

Licensed under Apache-2.0. The container includes PR-Agent under its corresponding open-source license.
