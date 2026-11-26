"""Unit tests for the shared N8nApiClient."""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from n8n_client import N8nApiClient, N8nApiError  # noqa: E402


def _mock_response(payload, status=200):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_client_requires_credentials():
    with pytest.raises(ValueError):
        N8nApiClient("", "key")
    with pytest.raises(ValueError):
        N8nApiClient("http://localhost:5678/api/v1", "")


def test_from_env_success_and_missing(monkeypatch):
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    monkeypatch.delenv("N8N_API_URL", raising=False)
    with pytest.raises(ValueError):
        N8nApiClient.from_env()

    monkeypatch.setenv("N8N_API_KEY", "test-key")
    monkeypatch.setenv("N8N_API_URL", "http://localhost:5678/api/v1/")
    client = N8nApiClient.from_env()
    assert client.api_url == "http://localhost:5678/api/v1"
    assert client.headers["X-N8N-API-KEY"] == "test-key"


@patch("n8n_client.time.sleep")
@patch("n8n_client.urllib.request.urlopen")
def test_retry_on_transient_503(mock_urlopen, mock_sleep):
    err = urllib.error.HTTPError(
        "http://localhost/api/v1/workflows", 503, "Service Unavailable", {}, io.BytesIO(b"busy")
    )
    mock_urlopen.side_effect = [err, _mock_response({"data": []})]

    client = N8nApiClient("http://localhost/api/v1", "key", max_retries=2, backoff_factor=0.1)
    result = client.request("GET", "/workflows")
    assert result == {"data": []}
    assert mock_urlopen.call_count == 2
    assert mock_sleep.call_count == 1


@patch("n8n_client.urllib.request.urlopen")
def test_non_retryable_400_raises_api_error(mock_urlopen):
    err = urllib.error.HTTPError(
        "http://localhost/api/v1/workflows", 400, "Bad Request", {}, io.BytesIO(b"invalid")
    )
    mock_urlopen.side_effect = err

    client = N8nApiClient("http://localhost/api/v1", "key", max_retries=2)
    with pytest.raises(N8nApiError) as exc_info:
        client.request("POST", "/workflows", payload={"name": "bad"})
    assert exc_info.value.status_code == 400
    assert "invalid" in exc_info.value.body


@patch("n8n_client.urllib.request.urlopen")
def test_get_workflow_returns_none_on_404(mock_urlopen):
    err = urllib.error.HTTPError(
        "http://localhost/api/v1/workflows/999", 404, "Not Found", {}, io.BytesIO(b"")
    )
    mock_urlopen.side_effect = err

    client = N8nApiClient("http://localhost/api/v1", "key")
    assert client.get_workflow("999") is None


@patch("n8n_client.urllib.request.urlopen")
def test_list_workflows_handles_cursor_pagination(mock_urlopen):
    page1 = _mock_response({"data": [{"id": "1", "name": "WF1"}], "nextCursor": "abc"})
    page2 = _mock_response({"data": [{"id": "2", "name": "WF2"}], "nextCursor": None})
    mock_urlopen.side_effect = [page1, page2]

    client = N8nApiClient("http://localhost/api/v1", "key")
    workflows = client.list_workflows(active_only=True, limit=1)
    assert [w["id"] for w in workflows] == ["1", "2"]
    assert mock_urlopen.call_count == 2
    second_req = mock_urlopen.call_args_list[1][0][0]
    assert "cursor=abc" in second_req.full_url
    assert "active=true" in second_req.full_url
