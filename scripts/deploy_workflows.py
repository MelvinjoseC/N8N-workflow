#!/usr/bin/env python3
import os
import sys
import glob
import json
import urllib.request
import urllib.error
import argparse

import time

DEFAULT_TIMEOUT = 30
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

def get_api_credentials(api_key_env, api_url_env):
    api_key = os.environ.get(api_key_env)
    api_url = os.environ.get(api_url_env)
    return api_key, api_url

def make_request(req, timeout=DEFAULT_TIMEOUT, max_retries=3, backoff_factor=1.0):
    """
    Executes an urllib request with timeout and exponential backoff retry logic.
    """
    retries = 0
    while True:
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS_CODES and retries < max_retries:
                retries += 1
                sleep_time = backoff_factor * (2 ** (retries - 1))
                time.sleep(sleep_time)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if retries < max_retries:
                retries += 1
                sleep_time = backoff_factor * (2 ** (retries - 1))
                time.sleep(sleep_time)
                continue
            raise

def check_workflow_exists(api_url, headers, workflow_id, timeout=DEFAULT_TIMEOUT):
    check_url = f"{api_url.rstrip('/')}/workflows/{workflow_id}"
    req = urllib.request.Request(check_url, headers=headers, method='GET')
    try:
        with make_request(req, timeout=timeout, max_retries=2, backoff_factor=0.2) as resp:
            if resp.status == 200:
                return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        print(f"HTTP Error checking workflow {workflow_id}: {e.code} - {e.reason}")
    except Exception as e:
        print(f"Error checking workflow {workflow_id}: {str(e)}")
    return False

def backup_remote_workflow(api_url, headers, workflow_id, backup_dir):
    """
    Downloads existing remote workflow JSON and saves to backup_dir before overwrite.
    """
    if not backup_dir:
        return None
    os.makedirs(backup_dir, exist_ok=True)
    fetch_url = f"{api_url.rstrip('/')}/workflows/{workflow_id}"
    req = urllib.request.Request(fetch_url, headers=headers, method='GET')
    try:
        with make_request(req, timeout=DEFAULT_TIMEOUT) as resp:
            data = resp.read().decode('utf-8')
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f"{workflow_id}_{timestamp}.json")
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(data)
            print(f"Pre-deploy backup created: {backup_file}")
            return backup_file
    except Exception as e:
        print(f"Warning: Failed to create pre-deploy backup for {workflow_id}: {e}")
        return None

def deploy_workflow(api_url, headers, filepath, dry_run=False, backup_dir=None):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            workflow_data = json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {str(e)}")
        return False

    name = workflow_data.get('name')
    if not name:
        print(f"Error: Workflow in {filepath} is missing a name.")
        return False

    payload = {
        'name': name,
        'nodes': workflow_data.get('nodes', []),
        'connections': workflow_data.get('connections', {}),
        'settings': workflow_data.get('settings', {}),
        'active': workflow_data.get('active', False)
    }

    workflow_id = workflow_data.get('id')
    base_url = api_url.rstrip('/')
    url = f"{base_url}/workflows"
    method = 'POST'

    if workflow_id:
        exists = check_workflow_exists(api_url, headers, workflow_id)
        if exists:
            if dry_run:
                print(f"[DRY-RUN] Workflow '{name}' (ID: {workflow_id}) exists on target. Would perform UPDATE (PUT).")
                return True
            if backup_dir:
                backup_remote_workflow(api_url, headers, workflow_id, backup_dir)
            print(f"Workflow ID {workflow_id} exists on target. Performing UPDATE (PUT).")
            url = f"{base_url}/workflows/{workflow_id}"
            method = 'PUT'
        else:
            if dry_run:
                print(f"[DRY-RUN] Workflow '{name}' (ID: {workflow_id}) not found on target. Would perform CREATE (POST).")
                return True
            print(f"Workflow ID {workflow_id} not found on target. Creating NEW (POST) with original ID.")
            payload['id'] = workflow_id
    elif dry_run:
        print(f"[DRY-RUN] Workflow '{name}' has no ID. Would perform CREATE (POST).")
        return True

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method=method
    )

    try:
        with make_request(req, timeout=DEFAULT_TIMEOUT) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            print(f"Successfully deployed: {result.get('name')} (ID: {result.get('id')})")
            return True
    except urllib.error.HTTPError as e:
        print(f"Failed to deploy workflow {name}: {e.code} - {e.reason}")
        try:
            print(e.read().decode('utf-8'))
        except Exception:
            pass
    except Exception as e:
        print(f"Unexpected error deploying workflow {name}: {str(e)}")
    return False

def main():
    parser = argparse.ArgumentParser(description="Sync local JSON workflows with target n8n instance.")
    parser.add_argument("directory", help="Directory containing JSON workflows")
    parser.add_argument("--key-env", default="N8N_API_KEY", help="Environment variable name for API key")
    parser.add_argument("--url-env", default="N8N_API_URL", help="Environment variable name for API URL")
    parser.add_argument("--dry-run", action="store_true", help="Simulate deployment actions without modifying remote n8n instance")
    parser.add_argument("--backup-dir", default=None, help="Directory to store pre-deploy backups of remote workflows")
    args = parser.parse_args()

    api_key, api_url = get_api_credentials(args.key_env, args.url_env)
    if not api_key or not api_url:
        print(f"Error: API Credentials missing ({args.key_env} or {args.url_env} not set).")
        sys.exit(1)

    headers = {
        'X-N8N-API-KEY': api_key,
        'Content-Type': 'application/json'
    }

    workflow_files = glob.glob(os.path.join(args.directory, '*.json'))
    mode_str = " (DRY-RUN MODE)" if args.dry_run else ""
    print(f"Found {len(workflow_files)} workflows to deploy{mode_str}.")

    success_count = 0
    for file in workflow_files:
        print(f"\nProcessing {file}...")
        if deploy_workflow(api_url, headers, file, dry_run=args.dry_run, backup_dir=args.backup_dir):
            success_count += 1

    print(f"\nDeployment complete: {success_count}/{len(workflow_files)} workflows processed.")
    if success_count < len(workflow_files):
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
