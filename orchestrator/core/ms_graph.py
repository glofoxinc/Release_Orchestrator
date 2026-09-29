"""Microsoft Graph auth helper (SharePoint upload + Teams scheduling).

Uses the OAuth2 client-credentials flow. Credentials come from env only —
never from workspace.yaml — so secrets stay out of git:

  MS_GRAPH_TENANT_ID / MICROSOFT_TENANT_ID
  MS_GRAPH_CLIENT_ID / MICROSOFT_CLIENT_ID
  MS_GRAPH_CLIENT_SECRET / MICROSOFT_CLIENT_SECRET

Transport is injectable so unit tests never hit the network.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

TokenTransport = Callable[[str, dict[str, str]], tuple[int, dict[str, Any]]]
HttpTransport = Callable[
    [str, str, dict[str, str], bytes | None],
    tuple[int, dict[str, Any] | str | bytes],
]

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


def _env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class GraphCredentials:
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""

    @classmethod
    def from_env(cls) -> "GraphCredentials":
        return cls(
            tenant_id=_env("MS_GRAPH_TENANT_ID", "MICROSOFT_TENANT_ID"),
            client_id=_env("MS_GRAPH_CLIENT_ID", "MICROSOFT_CLIENT_ID"),
            client_secret=_env("MS_GRAPH_CLIENT_SECRET", "MICROSOFT_CLIENT_SECRET"),
        )

    def configured(self) -> bool:
        if _env("MS_GRAPH_ACCESS_TOKEN"):
            return True
        return bool(self.tenant_id and self.client_id and self.client_secret)

    def token_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"


@dataclass
class GraphToken:
    access_token: str
    expires_at: float = 0.0
    token_type: str = "Bearer"

    def valid(self, *, skew_seconds: float = 60.0) -> bool:
        return bool(self.access_token) and time.time() < (self.expires_at - skew_seconds)


@dataclass
class GraphClient:
    """Thin Graph client with cached token + injectable transports."""

    credentials: GraphCredentials = field(default_factory=GraphCredentials.from_env)
    token_transport: TokenTransport | None = None
    http_transport: HttpTransport | None = None
    _token: GraphToken | None = field(default=None, init=False, repr=False)

    def configured(self) -> bool:
        return self.credentials.configured() or bool(_env("MS_GRAPH_ACCESS_TOKEN"))

    def status(self) -> dict[str, Any]:
        creds = self.credentials
        return {
            "configured": creds.configured(),
            "tenant_set": bool(creds.tenant_id),
            "client_id_set": bool(creds.client_id),
            "client_secret_set": bool(creds.client_secret),
            "missing": [
                name
                for name, ok in (
                    ("MS_GRAPH_TENANT_ID", bool(creds.tenant_id)),
                    ("MS_GRAPH_CLIENT_ID", bool(creds.client_id)),
                    ("MS_GRAPH_CLIENT_SECRET", bool(creds.client_secret)),
                )
                if not ok
            ],
        }

    def get_access_token(self, *, force: bool = False) -> str:
        bearer = _env("MS_GRAPH_ACCESS_TOKEN")
        if bearer:
            return bearer
        if not force and self._token and self._token.valid():
            return self._token.access_token
        if not self.credentials.configured():
            raise RuntimeError(
                "Microsoft Graph credentials are not configured. "
                "Set MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, and MS_GRAPH_CLIENT_SECRET."
            )
        transport = self.token_transport or _default_token_transport()
        status, body = transport(
            self.credentials.token_url(),
            {
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
                "scope": GRAPH_SCOPE,
                "grant_type": "client_credentials",
            },
        )
        if status >= 400 or not isinstance(body, dict) or not body.get("access_token"):
            detail = body if isinstance(body, dict) else {"raw": body}
            raise RuntimeError(f"Graph token request failed (HTTP {status}): {detail}")
        expires_in = float(body.get("expires_in") or 3600)
        self._token = GraphToken(
            access_token=str(body["access_token"]),
            expires_at=time.time() + expires_in,
            token_type=str(body.get("token_type") or "Bearer"),
        )
        return self._token.access_token

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | str | bytes]:
        """Call Graph. ``path`` may be absolute or relative to ``/v1.0``."""
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path if path.startswith('/') else '/' + path}"
        headers = {
            "Accept": "application/json",
        }
        body: bytes | None = content
        if json_body is not None:
            import json

            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif content is not None:
            headers["Content-Type"] = content_type or "application/octet-stream"
        if extra_headers:
            headers.update(extra_headers)

        transport = self.http_transport or _default_http_transport()
        last_status = 0
        last_body: dict[str, Any] | str | bytes = {}
        for attempt in range(_MAX_RETRIES + 1):
            token = self.get_access_token(force=attempt > 0 and last_status == 401)
            call_headers = {**headers, "Authorization": f"Bearer {token}"}
            status, payload = transport(method.upper(), url, call_headers, body)
            last_status = status
            last_body = payload
            if status not in _RETRYABLE_STATUS_CODES or attempt >= _MAX_RETRIES:
                return status, payload
            if status == 429 and isinstance(payload, dict):
                delay = int(payload.get("retry_after") or 0)
            else:
                delay = 0
            if delay <= 0:
                retry_after_hdr = ""
                if isinstance(payload, dict):
                    retry_after_hdr = str(payload.get("Retry-After") or "")
                if retry_after_hdr.isdigit():
                    delay = int(retry_after_hdr)
            if delay <= 0:
                delay = int(_BACKOFF_BASE ** attempt)
            logger.debug(
                "Graph request retry %s/%s for HTTP %s on %s",
                attempt + 1,
                _MAX_RETRIES,
                status,
                path,
            )
            time.sleep(delay)
        return last_status, last_body


def _default_token_transport() -> TokenTransport:
    def _call(url: str, form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        import requests

        resp = requests.post(url, data=form, timeout=30)
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text}
        if not isinstance(payload, dict):
            payload = {"raw": payload}
        return resp.status_code, payload

    return _call


def _default_http_transport() -> HttpTransport:
    def _call(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, dict[str, Any] | str | bytes]:
        import requests

        resp = requests.request(method, url, headers=headers, data=body, timeout=60)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "application/json" in ctype:
            try:
                return resp.status_code, resp.json()
            except ValueError:
                return resp.status_code, resp.text
        if ctype.startswith("text/"):
            return resp.status_code, resp.text
        return resp.status_code, resp.content

    return _call


__all__ = [
    "GRAPH_BASE",
    "GRAPH_SCOPE",
    "GraphClient",
    "GraphCredentials",
    "GraphToken",
    "HttpTransport",
    "TokenTransport",
]
