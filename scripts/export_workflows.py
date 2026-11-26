#!/usr/bin/env python3
"""Export workflows from a running n8n instance to local sanitized JSON files."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from typing import Any

from n8n_client import N8nApiClient

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Convert a workflow name into a safe, snake_case filename."""
    clean = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", clean)


def sanitize_workflow_export(wf: dict[str, Any]) -> dict[str, Any]:
    """Normalize exported workflow structure and strip volatile server metadata."""
    meta = dict(wf.get("meta") or {})
    meta.pop("deployedAt", None)

    export_data: dict[str, Any] = {
        "name": wf.get("name", "unnamed_workflow"),
        "nodes": wf.get("nodes", []),
        "connections": wf.get("connections", {}),
        "active": wf.get("active", False),
        "settings": wf.get("settings", {}),
        "meta": meta,
    }
    if "id" in wf:
        export_data["id"] = wf["id"]
    if "tags" in wf and wf["tags"]:
        export_data["tags"] = wf["tags"]
    return export_data


def fetch_all_workflows(
    api_url: str,
    headers: dict[str, str],
    active_only: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve all workflows from the target n8n instance using cursor pagination."""
    try:
        client = N8nApiClient(
            api_url=api_url,
            api_key=headers.get("X-N8N-API-KEY", "dummy"),
        )
        return client.list_workflows(active_only=active_only)
    except Exception as exc:
        logger.error("Error fetching workflows from %s: %s", api_url, exc)
        return []


def _matches_tag(wf: dict[str, Any], tag_filter: str | None) -> bool:
    if not tag_filter:
        return True
    tags = wf.get("tags") or []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("name") == tag_filter:
            return True
        if isinstance(tag, str) and tag == tag_filter:
            return True
    return False


def export_workflows(
    api_url: str,
    headers: dict[str, str],
    output_dir: str,
    active_only: bool = False,
    tag_filter: str | None = None,
) -> int:
    """Export remote workflows and write sanitized JSON files to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    workflows = fetch_all_workflows(api_url, headers)
    if not workflows:
        logger.info("No workflows found or failed to fetch workflows.")
        return 0

    exported_count = 0
    for wf in workflows:
        name = wf.get("name", "unnamed_workflow")
        is_active = wf.get("active", False)

        if active_only and not is_active:
            continue
        if not _matches_tag(wf, tag_filter):
            continue

        filename = f"{sanitize_filename(name)}.json"
        filepath = os.path.join(output_dir, filename)
        export_data = sanitize_workflow_export(wf)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
            f.write("\n")

        logger.info("Exported: %s -> %s", name, filepath)
        exported_count += 1

    return exported_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export workflows from n8n instance to local directory."
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="workflows",
        help="Directory to save exported workflows",
    )
    parser.add_argument(
        "--key-env", default="N8N_API_KEY", help="Env var name for API key"
    )
    parser.add_argument(
        "--url-env", default="N8N_API_URL", help="Env var name for API URL"
    )
    parser.add_argument(
        "--active-only", action="store_true", help="Only export active workflows"
    )
    parser.add_argument(
        "--tag", default=None, help="Only export workflows matching this tag name"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    api_key = os.environ.get(args.key_env)
    api_url = os.environ.get(args.url_env)

    if not api_key or not api_url:
        logger.error(
            "API credentials missing (%s or %s not set).", args.key_env, args.url_env
        )
        sys.exit(1)

    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    count = export_workflows(
        api_url,
        headers,
        args.output_dir,
        active_only=args.active_only,
        tag_filter=args.tag,
    )
    logger.info("Successfully exported %d workflow(s) to '%s'.", count, args.output_dir)
    sys.exit(0)


if __name__ == "__main__":
    main()
