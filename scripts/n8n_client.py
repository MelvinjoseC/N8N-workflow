#!/usr/bin/env python3
"""Shared n8n REST API client with retry, backoff, and cursor pagination."""

from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class N8nApiError(Exception):
    """Raised when an n8n REST API request fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class N8nApiClient:
    """Lightweight HTTP client for the n8n Public REST API v1."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        if not api_url or not api_key:
            raise ValueError("Both api_url and api_key must be non-empty.")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    @classmethod
    def from_env(
        cls,
        key_env: str = "N8N_API_KEY",
        url_env: str = "N8N_API_URL",
        **kwargs: Any,
    ) -> N8nApiClient:
        """Instantiate an N8nApiClient from environment variables."""
        api_key = os.environ.get(key_env, "").strip()
        api_url = os.environ.get(url_env, "").strip()
        if not api_key or not api_url:
            raise ValueError(
                f"API credentials missing ({key_env} or {url_env} not set)."
            )
        return cls(api_url=api_url, api_key=api_key, **kwargs)

    @property
    def headers(self) -> dict[str, str]:
        """Default headers required for authenticated n8n API requests."""
        return {
            "X-N8N-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _compute_delay(self, attempt: int) -> float:
        base = self.backoff_factor * (2 ** (attempt - 1))
        jitter = random.uniform(0.0, 0.25 * base)  # nosec B311
        return base + jitter

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry and exponential backoff."""
        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.api_url}{clean_path}"
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, headers=self.headers, method=method.upper()
        )

        retries = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8")
                except Exception:
                    pass
                if exc.code in RETRY_STATUS_CODES and retries < self.max_retries:
                    retries += 1
                    delay = self._compute_delay(retries)
                    logger.warning(
                        "HTTP %s on %s %s; retrying in %.2fs (%d/%d)",
                        exc.code,
                        method,
                        clean_path,
                        delay,
                        retries,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    continue
                raise N8nApiError(
                    f"HTTP {exc.code} {exc.reason} for {method} {clean_path}",
                    status_code=exc.code,
                    body=body,
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if retries < self.max_retries:
                    retries += 1
                    delay = self._compute_delay(retries)
                    logger.warning(
                        "Network error on %s %s (%s); retrying in %.2fs (%d/%d)",
                        method,
                        clean_path,
                        exc,
                        delay,
                        retries,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    continue
                raise N8nApiError(
                    f"Network error for {method} {clean_path}: {exc}"
                ) from exc

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """Fetch a single workflow by ID, returning None if not found (404)."""
        try:
            return self.request("GET", f"/workflows/{workflow_id}")
        except N8nApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    def list_workflows(
        self,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List all workflows using cursor pagination."""
        results: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {"limit": limit}
            if active_only:
                params["active"] = "true"
            if cursor:
                params["cursor"] = cursor

            resp = self.request("GET", "/workflows", params=params)
            if isinstance(resp, list):
                results.extend(resp)
                break

            page_items = resp.get("data", [])
            results.extend(page_items)
            cursor = resp.get("nextCursor")
            if not cursor:
                break

        return results

    def create_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new workflow on the remote n8n instance."""
        return self.request("POST", "/workflows", payload=payload)

    def update_workflow(
        self, workflow_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing workflow on the remote n8n instance."""
        return self.request("PUT", f"/workflows/{workflow_id}", payload=payload)
