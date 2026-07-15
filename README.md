# PR Review Runner

PR Review Runner publishes AI-assisted pull request analysis as a native GitHub Review with a summary and line comments. It handles `/describe`, `/review`, and `/ask` directly and passes other PR-Agent slash commands through.

The runner is built on [PR-Agent](https://github.com/qodo-ai/pr-agent). Thanks to the PR-Agent project and its contributors. This project is independently maintained and is not affiliated with Qodo or GitHub.

## Usage

The workflow must use `pull_request_target` only without checking out or executing pull request code. The image reads pull request data through the GitHub API.

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
        github.event_name == 'pull_request_target' ||
        github.event.issue.pull_request != null
      )
    concurrency:
      group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.event.issue.number }}
      cancel-in-progress: ${{ github.event_name == 'pull_request_target' }}
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Run PR Review
        uses: docker://ghcr.io/infinitypacer/pr-review-runner:latest
        env:
          GITHUB_TOKEN: ${{ github.token }}
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          OPENAI_API_BASE: ${{ secrets.OPENAI_API_BASE }}
```

`GITHUB_TOKEN` is the short-lived token created by GitHub Actions. Do not create a personal token for the runner.

## Commands

- `/describe` updates the owned PR summary block without replacing contributor text.
- `/review` publishes a native `PR-Agent Code Review` summary and eligible line comments.
- `/ask <question>` answers a question about the pull request.

Manual commands accept `created` and `edited` comments from `OWNER`, `MEMBER`, `COLLABORATOR`, `CONTRIBUTOR`, and `FIRST_TIME_CONTRIBUTOR` by default. Other PR-Agent commands such as `/improve` and `/update_changelog` pass through by default. Set `PRR_DISABLED_COMMANDS` to disable commands in a consuming workflow.

Pull requests carrying the `skip pr-agent` label or a title beginning with `[Auto]` or `Auto` are skipped for every route.

## Configuration

All overrides are optional. Defaults preserve the validated model routes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRR_DESCRIBE_MODEL` | `gpt-5.6-terra` | Description model |
| `PRR_DESCRIBE_REASONING_EFFORT` | `medium` | Description reasoning effort |
| `PRR_AUTO_REVIEW_MODEL` | `gpt-5.6-sol` | Automatic Review model |
| `PRR_AUTO_REVIEW_REASONING_EFFORT` | `xhigh` | Automatic Review reasoning effort |
| `PRR_MANUAL_REVIEW_MODEL` | `gpt-5.6-sol` | Manual `/review` model |
| `PRR_MANUAL_REVIEW_REASONING_EFFORT` | `xhigh` | Manual Review reasoning effort |
| `PRR_ASK_MODEL` | `gpt-5.6-terra` | `/ask` model |
| `PRR_ASK_REASONING_EFFORT` | `high` | `/ask` reasoning effort |
| `PRR_PASSTHROUGH_MODEL` | `gpt-5.6-sol` | Other PR-Agent command model |
| `PRR_PASSTHROUGH_REASONING_EFFORT` | `xhigh` | Other PR-Agent command reasoning effort |
| `PRR_FALLBACK_MODELS` | `["gpt-5.5", "gpt-5.4"]` | JSON fallback model list |
| `PRR_CUSTOM_MODEL_MAX_TOKENS` | `1050000` | Custom model context limit |
| `PRR_AUTO_REVIEW_SCOPE` | `all` | `all`, `forks`, or `manual` |
| `PRR_ALLOWED_ASSOCIATIONS` | See above | JSON manual-command role list |
| `PRR_DISABLED_COMMANDS` | `[]` | JSON command denylist, for example `["/improve"]` |
| `PRR_MAX_FINDINGS` | `4` | Maximum structured Review findings |

Set `PRR_AUTO_REVIEW_SCOPE: forks` when automatic processing should run only for fork pull requests. Manual commands remain available for same-repository pull requests.

## Review Output

High, medium, and low findings use visible priority badges. A finding without a recognized classification remains visible without a badge. If no actionable issue is found, the runner publishes only a natural-language Review summary.

The publisher rejects stale analysis when the PR head changes, avoids repeating an identical Review for the same head, and avoids duplicating line comments at an existing location. It removes only historical issue comments carrying runner-owned markers.

## Image Releases

Image publication is manual and offers only `edge` and `release` modes. Edge mode builds `main` as the fixed `edge` tag for pre-release validation. Release mode requires the edge image version to match the local package version.

Release mode promotes that exact edge digest without rebuilding it. The resulting image tags are the current local package version and `latest`.

## License

Licensed under Apache-2.0. The container includes PR-Agent under its corresponding open-source license.
