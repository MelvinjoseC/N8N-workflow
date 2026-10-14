#!/usr/bin/env python3
import os
import sys
import json
import re
import argparse

# Suspected hardcoded credential patterns and default configuration
DEFAULT_CONFIG = {
    "rules": {
        "requireErrorWorkflow": True,
        "checkUniqueNodeNames": True,
        "detectDisabledNodes": True,
        "checkWebhookAuth": True,
        "checkHttpTimeout": True,
        "checkTypeVersion": True,
        "scanHardcodedSecrets": True,
        "validateConnections": True
    },
    "secretKeywords": ["key", "secret", "password", "token", "auth", "pwd"],
    "excludedSecretValues": ["dummy", "test", "localhost", "127.0.0.1", "none"],
    "minHttpTimeoutMs": 1000
}

CRED_KEYWORDS = DEFAULT_CONFIG["secretKeywords"]
EXCLUDED_VALUES = DEFAULT_CONFIG["excludedSecretValues"]

def load_config(config_path=None):
    """
    Loads linter configuration from a JSON file, merging with default settings.
    """
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    target = config_path or ".n8n-lint.json"
    if target and os.path.exists(target):
        try:
            with open(target, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if "rules" in loaded and isinstance(loaded["rules"], dict):
                    config["rules"].update(loaded["rules"])
                if "secretKeywords" in loaded and isinstance(loaded["secretKeywords"], list):
                    config["secretKeywords"] = loaded["secretKeywords"]
                if "excludedSecretValues" in loaded and isinstance(loaded["excludedSecretValues"], list):
                    config["excludedSecretValues"] = loaded["excludedSecretValues"]
                if "minHttpTimeoutMs" in loaded:
                    config["minHttpTimeoutMs"] = loaded["minHttpTimeoutMs"]
        except Exception as e:
            print(f"Warning: Failed to load config from {target}: {e}")
    return config

def is_hardcoded_secret(value, excluded_values=None):
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
    excluded = excluded_values if excluded_values is not None else EXCLUDED_VALUES
    for dummy in excluded:
        if dummy in val_lower:
            return False
            
    # Check if value looks like a hex token or high entropy string
    if re.match(r'^[a-zA-Z0-9_\-]{16,}$', value):
        return True
        
    return False

def check_workflow_file(filepath, config=None):
    """
    Runs lint checks on a single n8n workflow JSON file.
    Returns a list of error strings and a list of warning strings.
    """
    if config is None:
        config = load_config()
        
    rules = config.get("rules", {})
    cred_keywords = config.get("secretKeywords", CRED_KEYWORDS)
    excluded_values = config.get("excludedSecretValues", EXCLUDED_VALUES)
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
    if rules.get("requireErrorWorkflow", True):
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
        if rules.get("checkUniqueNodeNames", True):
            if name in node_names:
                errors.append(f"Duplicate node name found: '{name}'")
            node_names.add(name)
        else:
            node_names.add(name)
        
        # Rule 3: Detect disabled nodes (debugging leftovers)
        if rules.get("detectDisabledNodes", True):
            if node.get("disabled") is True:
                warnings.append(f"Node '{name}' is disabled. Verify if it should be removed before production deployment.")

        # Rule 4: Webhook and HTTP authentication warnings
        if rules.get("checkWebhookAuth", True):
            if node_type == "n8n-nodes-base.webhook":
                auth = node.get("parameters", {}).get("authentication", "none")
                if auth == "none":
                    warnings.append(f"Webhook Node '{name}' does not configure authentication. Webhook will be publicly accessible.")

        # Rule 4b: Check HTTP Request nodes for explicit timeout configuration
        if rules.get("checkHttpTimeout", True):
            if node_type == "n8n-nodes-base.httpRequest":
                options = node.get("parameters", {}).get("options", {})
                if not isinstance(options, dict) or "timeout" not in options:
                    warnings.append(f"HTTP Request Node '{name}' has no explicit timeout configured. Default or missing timeouts can cause hung executions.")

        # Rule 4c: Check for deprecated or invalid node typeVersion (< 1)
        if rules.get("checkTypeVersion", True):
            type_version = node.get("typeVersion")
            if type_version is not None and isinstance(type_version, (int, float)) and type_version < 1:
                warnings.append(f"Node '{name}' uses invalid typeVersion ({type_version}). Version must be >= 1.")


        
        # Rule 5: Inspect parameters for hardcoded secrets
        parameters = node.get("parameters", {})
        
        def inspect_dict(d, path=""):
            for k, v in d.items():
                current_path = f"{path}.{k}" if path else k
                
                # Check for sensitive key names containing values
                if isinstance(v, str) and any(keyword in k.lower() for keyword in cred_keywords):
                    if is_hardcoded_secret(v, excluded_values=excluded_values):
                        errors.append(f"Node '{name}': Suspected hardcoded credential in parameter '{current_path}' (value starts with '{v[:4]}...')")
                        
                elif isinstance(v, dict):
                    inspect_dict(v, current_path)
                elif isinstance(v, list):
                    for idx, item in enumerate(v):
                        if isinstance(item, dict):
                            inspect_dict(item, f"{current_path}[{idx}]")

        if rules.get("scanHardcodedSecrets", True):
            inspect_dict(parameters)
        
    # Rule 6: Validate connections (no orphaned or undefined nodes referenced)
    if rules.get("validateConnections", True):
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

def colorize(text, color_code):
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"\033[{color_code}m{text}\033[0m"

def generate_report(results, report_format="text", output_file=None):
    """
    Generates report string in text, json, or junit XML format, and optionally saves to file.
    """
    total_errors = sum(len(r["errors"]) for r in results)
    total_warnings = sum(len(r["warnings"]) for r in results)
    
    if report_format == "json":
        data = {
            "summary": {
                "total_files": len(results),
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "passed": total_errors == 0
            },
            "files": results
        }
        content = json.dumps(data, indent=2)
    elif report_format == "junit":
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append(f'<testsuite name="n8n-workflow-linter" tests="{len(results)}" failures="{total_errors}" errors="0">')
        for r in results:
            lines.append(f'  <testcase classname="workflows" name="{r["file"]}">')
            if r["errors"]:
                msg = "; ".join(r["errors"])
                lines.append(f'    <failure message="Validation failed">{msg}</failure>')
            lines.append('  </testcase>')
        lines.append('</testsuite>')
        content = "\n".join(lines)
    else:
        content = None

    if output_file and content:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
            
    return content

def main():
    parser = argparse.ArgumentParser(description="Lint n8n workflow export files for production readiness.")
    parser.add_argument("target_path", help="Path to workflow JSON file or directory containing workflow JSON files")
    parser.add_argument("--config", default=None, help="Path to custom .n8n-lint.json configuration file")
    parser.add_argument("--fail-on-warnings", action="store_true", help="Fail and return exit code 1 even on warnings")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress non-error output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed inspection traces")
    parser.add_argument("--format", choices=["text", "json", "junit"], default="text", help="Output report format (text, json, junit)")
    parser.add_argument("--output", "-o", default=None, help="Save report output to specified file path")
    args = parser.parse_args()
        
    config = load_config(args.config)
    files_to_check = []
    
    if os.path.isfile(args.target_path):
        files_to_check.append(args.target_path)
    elif os.path.isdir(args.target_path):
        for root, _, files in os.walk(args.target_path):
            for file in files:
                if file.endswith(".json"):
                    files_to_check.append(os.path.join(root, file))
    else:
        print(colorize(f"Error: Target path '{args.target_path}' does not exist.", "31"))
        sys.exit(1)
        
    results = []
    total_errors = 0
    total_warnings = 0
    
    if not args.quiet and args.format == "text":
        print(colorize(f"Linting {len(files_to_check)} workflow file(s)...", "36"))
    
    for filepath in files_to_check:
        filename = os.path.basename(filepath)
        errors, warnings = check_workflow_file(filepath, config=config)
        results.append({
            "file": filename,
            "filepath": filepath,
            "errors": errors,
            "warnings": warnings,
            "passed": len(errors) == 0
        })
        
        if not args.quiet and args.format == "text":
            print(f"\nChecking [{colorize(filename, '1')}]...")
        
        if not errors and not warnings:
            if not args.quiet and args.format == "text":
                print(f"  [{colorize('OK', '32')}] Passed validation.")
        else:
            for warning in warnings:
                if args.format == "text":
                    print(f"  [{colorize('WARN', '33')}] Warning: {warning}")
                total_warnings += 1
            for error in errors:
                if args.format == "text":
                    print(f"  [{colorize('ERROR', '31')}] Error: {error}")
                total_errors += 1

    report_str = generate_report(results, report_format=args.format, output_file=args.output)
    if args.format in ["json", "junit"] and not args.output:
        print(report_str)
                
    if args.format == "text" and (not args.quiet or total_errors > 0 or total_warnings > 0):
        print("\n" + "="*40)
        status_color = "32" if total_errors == 0 else "31"
        print(f"Lint Summary: {colorize(str(total_errors) + ' error(s)', status_color)}, {colorize(str(total_warnings) + ' warning(s)', '33' if total_warnings else '32')} found.")
        print("="*40)
    
    if total_errors > 0 or (args.fail_on_warnings and total_warnings > 0):
        if args.format == "text":
            print("\n" + colorize("Linting FAILED. Please resolve issues.", "31"))
        sys.exit(1)
    else:
        if not args.quiet and args.format == "text":
            print("\n" + colorize("Linting PASSED.", "32"))
        sys.exit(0)

if __name__ == "__main__":
    main()
