FROM pragent/pr-agent:0.39.0-github_action@sha256:b253845caa8c7ff5ce8be78f32996647982bdd4890826a962b78eff2e385a825

LABEL org.opencontainers.image.title="PR Review Runner" \
      org.opencontainers.image.description="Publish PR-Agent analysis as native GitHub Reviews" \
      org.opencontainers.image.source="https://github.com/InfinityPacer/pr-review-runner" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY pr_review_runner /app/pr_review_runner

ENTRYPOINT ["python", "-m", "pr_review_runner"]
