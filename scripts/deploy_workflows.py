#!/usr/bin/env python3
"""Sync local n8n workflow JSON files with a target n8n instance."""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import logging
import os
import shutil
import subprocess  # nosec B404
import sys
import time
from typing import Any

from lint_workflows import check_workflow_file, load_config
from n8n_client import DEFAULT_TIMEOUT, N8nApiClient, N8nApiError

logger = logging.getLogger(__name__)


def get_api_credentials(
    api_key_env: str, api_url_env: str
) -> tuple[str | None, str | None]:
    """Retrieve API credentials from environment variables."""
    return os.environ.get(api_key_env), os.environ.get(api_url_env)


def _client_from_headers(api_url: str, headers: dict[str, str]) -> N8nApiClient:
    api_key = headers.get("X-N8N-API-KEY", "")
    return N8nApiClient(api_url=api_url, api_key=api_key, timeout=DEFAULT_TIMEOUT)


def check_workflow_exists(
    api_url: str,
    headers: dict[str, str],
    workflow_id: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """Return True if workflow_id exists on the remote n8n instance."""
    try:
        client = N8nApiClient(
            api_url=api_url,
            api_key=headers.get("X-N8N-API-KEY", "dummy"),
            timeout=timeout,
            max_retries=2,
            backoff_factor=0.2,
        )
        return client.get_workflow(workflow_id) is not None
    except N8nApiError as exc:
        logger.error("HTTP error checking workflow %s: %s", workflow_id, exc)
    except Exception as exc:
        logger.error("Error checking workflow %s: %s", workflow_id, exc)
    return False


def backup_remote_workflow(
    api_url: str,
    headers: dict[str, str],
    workflow_id: str,
    backup_dir: str | None,
) -> str | None:
    """Download existing remote workflow JSON and save to backup_dir before overwrite."""
    if not backup_dir:
        return None
    os.makedirs(backup_dir, exist_ok=True)
    try:
        client = _client_from_headers(api_url, headers)
        remote = client.get_workflow(workflow_id)
        if remote is None:
            return None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"{workflow_id}_{timestamp}.json")
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(remote, f, indent=2)
            f.write("\n")
        logger.info("Pre-deploy backup created: %s", backup_file)
        return backup_file
    except Exception as exc:
        logger.warning(
            "Failed to create pre-deploy backup for %s: %s", workflow_id, exc
        )
        return None


def get_git_commit_sha() -> str | None:
    """Return short git commit SHA if available, otherwise None."""
    git_bin = shutil.which("git")
    if not git_bin:
        return None
    try:
        res = subprocess.run(  # nosec B603
            [git_bin, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


def sort_workflow_files(files: list[str]) -> list[str]:
    """Sort workflow files deterministically, deploying global_error_handler first."""
    return sorted(
        files,
        key=lambda p: (
            0 if os.path.basename(p) == "global_error_handler.json" else 1,
            os.path.basename(p),
        ),
    )


def sanitize_payload(workflow_data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Build a clean n8n API payload stripping read-only server fields."""
    payload: dict[str, Any] = {
        "name": workflow_data["name"],
        "nodes": workflow_data.get("nodes", []),
        "connections": workflow_data.get("connections", {}),
        "settings": workflow_data.get("settings", {}),
        "active": workflow_data.get("active", False),
        "meta": meta,
    }
    if "tags" in workflow_data:
        payload["tags"] = workflow_data["tags"]
    return payload


def compute_workflow_diff(
    local_payload: dict[str, Any],
    remote_workflow: dict[str, Any],
    name: str,
) -> str:
    """Return a unified diff between remote and local workflow definitions."""
    comparable_keys = ("name", "nodes", "connections", "settings", "active")
    remote_norm = {k: remote_workflow.get(k) for k in comparable_keys}
    local_norm = {k: local_payload.get(k) for k in comparable_keys}

    remote_lines = json.dumps(remote_norm, indent=2, sort_keys=True).splitlines(keepends=True)
    local_lines = json.dumps(local_norm, indent=2, sort_keys=True).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            remote_lines,
            local_lines,
            fromfile=f"remote/{name}",
            tofile=f"local/{name}",
        )
    )


def deploy_workflow(
    api_url: str,
    headers: dict[str, str],
    filepath: str,
    dry_run: bool = False,
    backup_dir: str | None = None,
    git_commit: str | None = None,
    show_diff: bool = False,
) -> bool:
    """Deploy a single workflow JSON file to the target n8n instance."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            workflow_data: dict[str, Any] = json.load(f)
    except Exception as exc:
        logger.error("Error reading %s: %s", filepath, exc)
        return False

    name = workflow_data.get("name")
    if not name:
        logger.error("Workflow in %s is missing a 'name' field.", filepath)
        return False

    meta = dict(workflow_data.get("meta", {}))
    commit_sha = git_commit or get_git_commit_sha()
    if commit_sha:
        meta["gitCommit"] = commit_sha
        meta["deployedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    payload = sanitize_payload(workflow_data, meta)

    workflow_id = workflow_data.get("id")
    client = _client_from_headers(api_url, headers)
    is_update = False

    if workflow_id:
        exists = check_workflow_exists(api_url, headers, workflow_id)
        if exists:
            if show_diff:
                remote = client.get_workflow(workflow_id)
                if remote is not None:
                    diff_text = compute_workflow_diff(payload, remote, name)
                    if diff_text:
                        logger.info("Diff for '%s':\n%s", name, diff_text)
                    else:
                        logger.info("No changes detected for '%s'.", name)
            if dry_run:
                logger.info(
                    "[DRY-RUN] Workflow '%s' (ID: %s) exists. Would UPDATE (PUT).",
                    name,
                    workflow_id,
                )
                return True
            if backup_dir:
                backup_remote_workflow(api_url, headers, workflow_id, backup_dir)
            logger.info("Workflow ID %s exists. Performing UPDATE (PUT).", workflow_id)
            is_update = True
        else:
            if dry_run:
                logger.info(
                    "[DRY-RUN] Workflow '%s' (ID: %s) not found. Would CREATE (POST).",
                    name,
                    workflow_id,
                )
                return True
            logger.info(
                "Workflow ID %s not found. Creating NEW (POST) with original ID.",
                workflow_id,
            )
            payload["id"] = workflow_id
    elif dry_run:
        logger.info("[DRY-RUN] Workflow '%s' has no ID. Would CREATE (POST).", name)
        return True

    try:
        if is_update and workflow_id:
            result = client.update_workflow(workflow_id, payload)
        else:
            result = client.create_workflow(payload)
        logger.info(
            "Successfully deployed: %s (ID: %s)", result.get("name"), result.get("id")
        )
        return True
    except N8nApiError as exc:
        logger.error("Failed to deploy workflow %s: %s", name, exc)
        if exc.body:
            logger.error("Response body: %s", exc.body)
    except Exception as exc:
        logger.error("Unexpected error deploying workflow %s: %s", name, exc)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync local JSON workflows with target n8n instance."
    )
    parser.add_argument("directory", help="Directory containing JSON workflows")
    parser.add_argument(
        "--key-env", default="N8N_API_KEY", help="Env var name for API key"
    )
    parser.add_argument(
        "--url-env", default="N8N_API_URL", help="Env var name for API URL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate deployment actions without modifying remote n8n instance",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Directory to store pre-deploy backups of remote workflows",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show unified diff against remote workflows before deploying",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Run workflow linter before deploying and abort on errors",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    api_key, api_url = get_api_credentials(args.key_env, args.url_env)
    if not api_key or not api_url:
        logger.error(
            "API Credentials missing (%s or %s not set).", args.key_env, args.url_env
        )
        sys.exit(1)

    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    workflow_files = sort_workflow_files(
        glob.glob(os.path.join(args.directory, "*.json"))
    )

    if args.lint:
        lint_cfg = load_config()
        lint_failed = False
        for wf_file in workflow_files:
            errs, _ = check_workflow_file(wf_file, config=lint_cfg)
            if errs:
                lint_failed = True
                for err in errs:
                    logger.error("Lint error in %s: %s", wf_file, err)
        if lint_failed:
            logger.error("Pre-deploy lint check failed. Aborting deployment.")
            sys.exit(1)

    mode_str = " (DRY-RUN MODE)" if args.dry_run else ""
    logger.info("Found %d workflows to deploy%s.", len(workflow_files), mode_str)

    success_count = 0
    for file in workflow_files:
        logger.info("Processing %s...", file)
        if deploy_workflow(
            api_url,
            headers,
            file,
            dry_run=args.dry_run,
            backup_dir=args.backup_dir,
            show_diff=args.diff,
        ):
            success_count += 1

    logger.info(
        "Deployment complete: %d/%d workflows processed.",
        success_count,
        len(workflow_files),
    )
    sys.exit(0 if success_count == len(workflow_files) else 1)


if __name__ == "__main__":
    main()
