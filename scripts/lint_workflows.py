#!/usr/bin/env python3
import os
import sys
import json
import re
import argparse

# Suspected hardcoded credential patterns
CRED_KEYWORDS = ["key", "secret", "password", "token", "auth", "pwd"]
EXCLUDED_VALUES = ["dummy", "test", "localhost", "127.0.0.1", "none"]

def is_hardcoded_secret(value):
    """
    Checks if a string looks like a hardcoded secret.
    Avoids triggering on n8n expressions (e.g., {{ $env.VAR }}) or known dummy variables.
    """
    if not isinstance(value, str):
        return False
    
    # Ignore n8n expressions
    if value.startswith("=") or ("{{" in value and "}}" in value):
        return False
        
    # Ignore empty or extremely short values
    if len(value.strip()) < 5:
        return False
        
    # Check if value matches standard dummy placeholders
    val_lower = value.lower()
    for dummy in EXCLUDED_VALUES:
        if dummy in val_lower:
            return False
            
    # Check if value looks like a hex token or high entropy string
    if re.match(r'^[a-zA-Z0-9_\-]{16,}$', value):
        return True
        
    return False

def check_workflow_file(filepath):
    """
    Runs lint checks on a single n8n workflow JSON file.
    Returns a list of error strings and a list of warning strings.
    """
    errors = []
    warnings = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON format: {str(e)}"], []
    except Exception as e:
        return [f"Failed to read file: {str(e)}"], []
        
    # Check core structure
    if "nodes" not in workflow:
        errors.append("Missing core 'nodes' array.")
        return errors, warnings
        
    nodes = workflow.get("nodes", [])
    connections = workflow.get("connections", {})
    settings = workflow.get("settings", {})
    
    # Rule 1: Check if errorWorkflow is configured
    if "errorWorkflow" not in settings or not settings["errorWorkflow"]:
        # Allow Error Trigger workflow itself to not have an error handler
        is_error_handler = any(n.get("type") == "n8n-nodes-base.errorTrigger" for n in nodes)
        if not is_error_handler:
            warnings.append("No 'errorWorkflow' configured in settings. Centralized error handling is recommended.")

    node_names = set()
    
    # Traverse nodes
    for node in nodes:
        name = node.get("name", "Unnamed Node")
        node_type = node.get("type", "unknown")
        
        # Rule 2: Ensure unique node names
        if name in node_names:
            errors.append(f"Duplicate node name found: '{name}'")
        node_names.add(name)
        
        # Rule 3: Detect disabled nodes (debugging leftovers)
        if node.get("disabled") is True:
            warnings.append(f"Node '{name}' is disabled. Verify if it should be removed before production deployment.")

        # Rule 4: Webhook and HTTP authentication warnings
        if node_type == "n8n-nodes-base.webhook":
            auth = node.get("parameters", {}).get("authentication", "none")
            if auth == "none":
                warnings.append(f"Webhook Node '{name}' does not configure authentication. Webhook will be publicly accessible.")

        # Rule 4b: Check HTTP Request nodes for explicit timeout configuration
        if node_type == "n8n-nodes-base.httpRequest":
            options = node.get("parameters", {}).get("options", {})
            if not isinstance(options, dict) or "timeout" not in options:
                warnings.append(f"HTTP Request Node '{name}' has no explicit timeout configured. Default or missing timeouts can cause hung executions.")

        # Rule 4c: Check for deprecated or invalid node typeVersion (< 1)
        type_version = node.get("typeVersion")
        if type_version is not None and isinstance(type_version, (int, float)) and type_version < 1:
            warnings.append(f"Node '{name}' uses invalid typeVersion ({type_version}). Version must be >= 1.")


        
        # Rule 5: Inspect parameters for hardcoded secrets
        parameters = node.get("parameters", {})
        
        def inspect_dict(d, path=""):
            for k, v in d.items():
                current_path = f"{path}.{k}" if path else k
                
                # Check for sensitive key names containing values
                if isinstance(v, str) and any(keyword in k.lower() for keyword in CRED_KEYWORDS):
                    if is_hardcoded_secret(v):
                        errors.append(f"Node '{name}': Suspected hardcoded credential in parameter '{current_path}' (value starts with '{v[:4]}...')")
                        
                elif isinstance(v, dict):
                    inspect_dict(v, current_path)
                elif isinstance(v, list):
                    for idx, item in enumerate(v):
                        if isinstance(item, dict):
                            inspect_dict(item, f"{current_path}[{idx}]")

        inspect_dict(parameters)
        
    # Rule 6: Validate connections (no orphaned or undefined nodes referenced)
    for source_node, conn_types in connections.items():
        if source_node not in node_names:
            errors.append(f"Connections reference a source node '{source_node}' that does not exist in the 'nodes' array.")
            
        for conn_type, paths in conn_types.items():
            for path in paths:
                for target in path:
                    target_node = target.get("node")
                    if target_node and target_node not in node_names:
                        errors.append(f"Connection from '{source_node}' references target node '{target_node}' which does not exist in the 'nodes' array.")

    return errors, warnings

def main():
    parser = argparse.ArgumentParser(description="Lint n8n workflow export files for production readiness.")
    parser.add_argument("target_path", help="Path to workflow JSON file or directory containing workflow JSON files")
    parser.add_argument("--fail-on-warnings", action="store_true", help="Fail and return exit code 1 even on warnings")
    args = parser.parse_args()
        
    files_to_check = []
    
    if os.path.isfile(args.target_path):
        files_to_check.append(args.target_path)
    elif os.path.isdir(args.target_path):
        for root, _, files in os.walk(args.target_path):
            for file in files:
                if file.endswith(".json"):
                    files_to_check.append(os.path.join(root, file))
    else:
        print(f"Error: Target path '{args.target_path}' does not exist.")
        sys.exit(1)
        
    total_errors = 0
    total_warnings = 0
    print(f"Linting {len(files_to_check)} workflow file(s)...")
    
    for filepath in files_to_check:
        filename = os.path.basename(filepath)
        print(f"\nChecking [{filename}]...")
        errors, warnings = check_workflow_file(filepath)
        
        if not errors and not warnings:
            print("  [OK] Passed validation.")
        else:
            for warning in warnings:
                print(f"  [WARN] Warning: {warning}")
                total_warnings += 1
            for error in errors:
                print(f"  [ERROR] Error: {error}")
                total_errors += 1
                
    print("\n" + "="*40)
    print(f"Lint Summary: {total_errors} error(s), {total_warnings} warning(s) found.")
    print("="*40)
    
    if total_errors > 0 or (args.fail_on_warnings and total_warnings > 0):
        print("\nLinting FAILED. Please resolve issues.")
        sys.exit(1)
    else:
        print("\nLinting PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
