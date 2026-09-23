"""Thin, dependency-injectable Atlassian REST client.

Used by both ``jira-release-tool`` and ``weekly-update-tool`` for Jira and
Confluence REST calls. Designed so that real HTTP calls are only made via a
single injected ``transport`` callable, which makes it trivial to unit-test
without network IO.

The existing ``jira_client.py`` module in ``jira-release-tool`` continues to
work as the product-specific high-level client — this module is the shared
foundation both projects can rely on.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)


class AtlassianError(RuntimeError):
    """Raised when an Atlassian API call fails in a non-retriable way."""

    def __init__(self, status: int, body: str, url: str = ""):
        super().__init__(f"{status} from {url}: {body[:200]}")
        self.status = status
        self.body = body
        self.url = url


class AtlassianTransient(AtlassianError):
    """Subclass raised for 5xx and 429 — intended for retry eligibility checks."""


@dataclass
class AtlassianCredentials:
    """Cloud-style basic auth credentials."""

    email: str
    api_token: str
    base_url: str

    def basic_header(self) -> str:
        raw = f"{self.email}:{self.api_token}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    @classmethod
    def from_env(
        cls,
        email_var: str = "JIRA_EMAIL",
        token_var: str = "JIRA_API_TOKEN",
        base_var: str = "JIRA_BASE_URL",
    ) -> "AtlassianCredentials":
        email = os.environ.get(email_var, "")
        token = os.environ.get(token_var, "")
        base = os.environ.get(base_var, "")
        if not (email and token and base):
            raise AtlassianError(
                0,
                f"Missing Atlassian credentials (need {email_var}, {token_var}, {base_var})",
                base,
            )
        return cls(email=email, api_token=token, base_url=base)


@dataclass
class HttpResponse:
    """Shape returned by the injected ``transport`` callable."""

    status: int
    body: str
    headers: Mapping[str, str]

    def json(self) -> Any:
        if not self.body:
            return {}
        return json.loads(self.body)


Transport = Callable[[str, str, dict[str, Any] | None, Mapping[str, str]], HttpResponse]


def default_transport() -> Transport:
    """Return a transport that delegates to ``requests`` if installed.

    The test-suite supplies a fake transport so this code path is not
    exercised in tests; we keep it thin and lazy.
    """

    def _call(method: str, url: str, payload: dict[str, Any] | None, headers: Mapping[str, str]) -> HttpResponse:
        import requests  # lazy import for optional-dependency resilience

        resp = requests.request(
            method=method,
            url=url,
            data=json.dumps(payload) if payload is not None else None,
            headers=dict(headers),
            timeout=float(os.environ.get("ATLASSIAN_HTTP_TIMEOUT", "30")),
        )
        return HttpResponse(status=resp.status_code, body=resp.text, headers=resp.headers)

    return _call


class AtlassianClient:
    """Minimal Jira + Confluence Cloud REST client.

    All network IO flows through ``transport`` (injected), making this class
    fully testable without mocking ``requests`` directly.
    """

    def __init__(
        self,
        credentials: AtlassianCredentials,
        *,
        transport: Transport | None = None,
        user_agent: str = "abc-bi-atlassian-client/1.0",
    ):
        self.creds = credentials
        self._transport = transport or default_transport()
        self._user_agent = user_agent

    # ── low-level ────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.creds.basic_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self._user_agent,
        }

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> HttpResponse:
        url = path if path.startswith("http") else f"{self.creds.base_url.rstrip('/')}{path}"
        resp = self._transport(method.upper(), url, payload, self._headers())
        if 200 <= resp.status < 300:
            return resp
        if resp.status == 429 or 500 <= resp.status < 600:
            raise AtlassianTransient(resp.status, resp.body, url)
        raise AtlassianError(resp.status, resp.body, url)

    def get(self, path: str) -> Any:
        return self.request("GET", path).json()

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload).json()

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PUT", path, payload).json()

    # ── Jira convenience ─────────────────────────────────────────
    def get_issue(self, key: str, *, fields: str | None = None) -> dict[str, Any]:
        path = f"/rest/api/3/issue/{key}"
        if fields:
            path += f"?fields={fields}"
        return self.get(path)

    def search_jql(
        self,
        jql: str,
        *,
        fields: list[str] | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields or ["summary", "status"],
        }
        return self.post("/rest/api/3/search", payload)

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        payload: dict[str, Any] = {"transition": {"id": transition_id}}
        if comment:
            payload["update"] = {"comment": [{"add": {"body": comment}}]}
        self.post(f"/rest/api/3/issue/{key}/transitions", payload)

    def add_label(self, key: str, label: str) -> None:
        self.request("PUT", f"/rest/api/3/issue/{key}", {"update": {"labels": [{"add": label}]}})

    # ── Confluence convenience (v2 API) ──────────────────────────
    def confluence_create_page(
        self,
        space_id: str,
        title: str,
        storage_body: str,
        *,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": storage_body,
            },
        }
        if parent_id:
            payload["parentId"] = parent_id
        return self.post("/wiki/api/v2/pages", payload)

    def confluence_update_page(
        self,
        page_id: str,
        *,
        title: str,
        storage_body: str,
        version_number: int,
    ) -> dict[str, Any]:
        payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "version": {"number": version_number},
            "body": {
                "representation": "storage",
                "value": storage_body,
            },
        }
        return self.put(f"/wiki/api/v2/pages/{page_id}", payload)

    def confluence_get_page(self, page_id: str) -> dict[str, Any]:
        return self.get(f"/wiki/api/v2/pages/{page_id}")

    def confluence_find_page_by_title(
        self,
        space_id: str,
        title: str,
    ) -> dict[str, Any] | None:
        """Look up a page by exact title within a space.

        Returns ``None`` if the page does not exist.
        """
        import urllib.parse as ul

        encoded = ul.quote(title, safe="")
        data = self.get(f"/wiki/api/v2/pages?spaceId={space_id}&title={encoded}&limit=1")
        results = data.get("results", []) if isinstance(data, dict) else []
        return results[0] if results else None


__all__ = [
    "AtlassianClient",
    "AtlassianCredentials",
    "AtlassianError",
    "AtlassianTransient",
    "HttpResponse",
    "Transport",
    "default_transport",
]
