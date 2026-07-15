"""Small GitHub REST client scoped to pull request review operations."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class GitHubApiError(RuntimeError):
    """Raised when GitHub rejects a repository operation."""


class GitHubApi:
    """Call GitHub with the workflow's short-lived repository token."""

    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self._token = token
        self._api_url = api_url.rstrip("/")

    def _request(self, method: str, endpoint: str, payload: dict | None = None) -> tuple[Any, object]:
        url = endpoint if endpoint.startswith("https://") else f"{self._api_url}/{endpoint.lstrip('/')}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "pr-review-runner",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read()
                return (json.loads(body) if body else None), response.headers
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise GitHubApiError(f"GitHub API {method} {endpoint} failed with {error.code}: {detail}") from error

    def get(self, endpoint: str) -> Any:
        return self._request("GET", endpoint)[0]

    def post(self, endpoint: str, payload: dict) -> Any:
        return self._request("POST", endpoint, payload)[0]

    def patch(self, endpoint: str, payload: dict) -> Any:
        return self._request("PATCH", endpoint, payload)[0]

    def delete(self, endpoint: str) -> None:
        self._request("DELETE", endpoint)

    def paginate(self, endpoint: str) -> list[dict]:
        """Follow GitHub Link headers without assuming a result count."""
        items: list[dict] = []
        next_endpoint = endpoint
        while next_endpoint:
            page, headers = self._request("GET", next_endpoint)
            if not isinstance(page, list):
                raise GitHubApiError(f"GitHub API pagination expected a list from {endpoint}")
            items.extend(page)
            link = str(headers.get("Link") or "")
            match = re.search(r'<([^>]+)>; rel="next"', link)
            next_endpoint = match.group(1) if match else ""
        return items
