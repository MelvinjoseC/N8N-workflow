"""Unit tests for scripts/healthcheck.py."""

from __future__ import annotations

import io
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import healthcheck  # noqa: E402


@patch("healthcheck.urllib.request.urlopen")
def test_check_http_endpoint_healthy(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    res = healthcheck.check_http_endpoint("n8n", "http://localhost:5678/healthz")
    assert res["healthy"] is True
    assert res["status_code"] == 200
    assert res["error"] is None


@patch("healthcheck.urllib.request.urlopen")
def test_check_http_endpoint_http_error(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "http://localhost:5678/healthz", 503, "Unavailable", {}, io.BytesIO(b"")
    )
    res = healthcheck.check_http_endpoint("n8n", "http://localhost:5678/healthz")
    assert res["healthy"] is False
    assert res["status_code"] == 503
    assert "503" in res["error"]


@patch("healthcheck.socket.create_connection")
def test_check_tcp_port_success_and_failure(mock_conn):
    mock_conn.return_value.__enter__ = MagicMock()
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)
    ok = healthcheck.check_tcp_port("postgres", "localhost", 5432)
    assert ok["healthy"] is True

    mock_conn.side_effect = OSError("Connection refused")
    fail = healthcheck.check_tcp_port("redis", "localhost", 6379)
    assert fail["healthy"] is False
    assert "Connection refused" in fail["error"]


@patch("healthcheck.check_tcp_port")
@patch("healthcheck.check_http_endpoint")
def test_run_healthchecks_combines_services(mock_http, mock_tcp):
    mock_http.return_value = {"service": "http", "healthy": True}
    mock_tcp.return_value = {"service": "tcp", "healthy": True}

    results = healthcheck.run_healthchecks(
        n8n_url="http://localhost:5678",
        gotenberg_url="http://localhost:3000",
        pg_host="postgres",
        redis_host="redis",
    )
    assert len(results) == 4
    assert mock_http.call_count == 2
    assert mock_tcp.call_count == 2
