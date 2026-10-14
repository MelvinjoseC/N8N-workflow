#!/usr/bin/env python3
"""
Utility script to export workflows from a running n8n instance to local JSON files.
Supports sanitization, filtering by active status, and custom output directories.
"""

import os
import sys
import json
import re
import urllib.request
import urllib.error
import argparse

def sanitize_filename(name):
    """
    Converts a workflow name into a safe, snake_case filename.
    """
    clean = re.sub(r'[^\w\s-]', '', name).strip().lower()
    return re.sub(r'[-\s]+', '_', clean)

def fetch_all_workflows(api_url, headers):
    """
    Retrieves all workflows from the target n8n instance via the REST API.
    """
    url = f"{api_url.rstrip('/')}/workflows"
    req = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('data', data if isinstance(data, list) else [])
    except Exception as e:
        print(f"Error fetching workflows from {url}: {e}")
        return []

def export_workflows(api_url, headers, output_dir, active_only=False):
    """
    Exports remote workflows and writes sanitized JSON files to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    workflows = fetch_all_workflows(api_url, headers)
    if not workflows:
        print("No workflows found or failed to fetch workflows.")
        return 0

    exported_count = 0
    for wf in workflows:
        name = wf.get('name', 'unnamed_workflow')
        is_active = wf.get('active', False)
        
        if active_only and not is_active:
            continue

        filename = f"{sanitize_filename(name)}.json"
        filepath = os.path.join(output_dir, filename)

        # Structure payload cleanly
        export_data = {
            "name": name,
            "nodes": wf.get("nodes", []),
            "connections": wf.get("connections", {}),
            "active": is_active,
            "settings": wf.get("settings", {}),
            "meta": wf.get("meta", {})
        }
        if "id" in wf:
            export_data["id"] = wf["id"]

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)

        print(f"Exported: {name} -> {filepath}")
        exported_count += 1

    return exported_count

def main():
    parser = argparse.ArgumentParser(description="Export workflows from n8n instance to local directory.")
    parser.add_argument("--output-dir", "-o", default="workflows", help="Directory to save exported workflows")
    parser.add_argument("--key-env", default="N8N_API_KEY", help="Environment variable name for API key")
    parser.add_argument("--url-env", default="N8N_API_URL", help="Environment variable name for API URL")
    parser.add_argument("--active-only", action="store_true", help="Only export active workflows")
    args = parser.parse_args()

    api_key = os.environ.get(args.key_env)
    api_url = os.environ.get(args.url_env)

    if not api_key or not api_url:
        print(f"Error: API credentials missing ({args.key_env} or {args.url_env} not set).")
        sys.exit(1)

    headers = {
        'X-N8N-API-KEY': api_key,
        'Content-Type': 'application/json'
    }

    count = export_workflows(api_url, headers, args.output_dir, active_only=args.active_only)
    print(f"\nSuccessfully exported {count} workflow(s) to '{args.output_dir}'.")
    sys.exit(0)

if __name__ == "__main__":
    main()
