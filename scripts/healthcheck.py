#!/usr/bin/env python3
"""Production stack healthcheck utility for n8n, Gotenberg, PostgreSQL, and Redis."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def check_http_endpoint(name: str, url: str, timeout: int = 5) -> dict[str, Any]:
    """Probe an HTTP health endpoint and measure latency in milliseconds."""
    start = time.monotonic()
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            healthy = 200 <= resp.status < 300
            return {
                "service": name,
                "target": url,
                "healthy": healthy,
                "status_code": resp.status,
                "latency_ms": latency_ms,
                "error": None if healthy else f"Unexpected HTTP {resp.status}",
            }
    except urllib.error.HTTPError as exc:
        return {
            "service": name,
            "target": url,
            "healthy": False,
            "status_code": exc.code,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except Exception as exc:
        return {
            "service": name,
            "target": url,
            "healthy": False,
            "status_code": None,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
            "error": str(exc),
        }


def check_tcp_port(name: str, host: str, port: int, timeout: int = 3) -> dict[str, Any]:
    """Verify TCP connectivity to a backing service (PostgreSQL, Redis)."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {
                "service": name,
                "target": f"{host}:{port}",
                "healthy": True,
                "latency_ms": latency_ms,
                "error": None,
            }
    except Exception as exc:
        return {
            "service": name,
            "target": f"{host}:{port}",
            "healthy": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
            "error": str(exc),
        }


def run_healthchecks(
    n8n_url: str,
    gotenberg_url: str | None = None,
    pg_host: str | None = None,
    pg_port: int = 5432,
    redis_host: str | None = None,
    redis_port: int = 6379,
    timeout: int = 5,
) -> list[dict[str, Any]]:
    """Run all configured healthchecks and return per-service results."""
    results = [
        check_http_endpoint("n8n", f"{n8n_url.rstrip('/')}/healthz", timeout=timeout)
    ]
    if gotenberg_url:
        results.append(
            check_http_endpoint(
                "gotenberg", f"{gotenberg_url.rstrip('/')}/health", timeout=timeout
            )
        )
    if pg_host:
        results.append(check_tcp_port("postgres", pg_host, pg_port, timeout=timeout))
    if redis_host:
        results.append(check_tcp_port("redis", redis_host, redis_port, timeout=timeout))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe health of n8n and supporting stack services."
    )
    parser.add_argument(
        "--n8n-url",
        default=os.environ.get("N8N_HEALTH_URL", "http://localhost:5678"),
        help="Base URL for n8n instance",
    )
    parser.add_argument(
        "--gotenberg-url",
        default=os.environ.get("GOTENBERG_URL", "http://localhost:3000"),
        help="Base URL for Gotenberg service",
    )
    parser.add_argument("--pg-host", default=None, help="Optional PostgreSQL host")
    parser.add_argument("--pg-port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--redis-host", default=None, help="Optional Redis host")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--timeout", type=int, default=5, help="Probe timeout seconds")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    args = parser.parse_args()

    results = run_healthchecks(
        n8n_url=args.n8n_url,
        gotenberg_url=args.gotenberg_url,
        pg_host=args.pg_host,
        pg_port=args.pg_port,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        timeout=args.timeout,
    )
    all_healthy = all(r["healthy"] for r in results)

    if args.json_output:
        print(json.dumps({"healthy": all_healthy, "checks": results}, indent=2))
    else:
        for item in results:
            status = "OK" if item["healthy"] else "FAIL"
            detail = f"{item['latency_ms']}ms" if item["healthy"] else item["error"]
            print(f"[{status}] {item['service']} ({item['target']}): {detail}")

    sys.exit(0 if all_healthy else 1)


if __name__ == "__main__":
    main()
