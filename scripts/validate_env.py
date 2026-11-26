#!/usr/bin/env python3
"""
Validates environment configuration (.env) against .env.example.
Audits for missing required keys, unrotated placeholder passwords, and weak encryption keys.
"""

import argparse
import json
import os
import sys

PLACEHOLDER_SUBSTRINGS = ["change-me", "example.com", "dummy", "replace-me"]
PASSWORD_KEYS = (
    "DB_POSTGRESDB_PASSWORD",
    "QUEUE_BULL_REDIS_PASSWORD",
    "N8N_BASIC_AUTH_PASSWORD",
)
MIN_PASSWORD_LENGTH = 12

def parse_env_file(filepath):
    """
    Parses a .env file and returns a dictionary of key-value pairs.
    """
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                env_vars[key.strip()] = val.strip().strip("'\"")
    return env_vars

def audit_environment(env_dict, example_dict, allow_placeholders=False):
    """
    Audits environment variables against example template.
    Returns (errors, warnings).
    """
    errors = []
    warnings = []

    # Check for missing variables defined in template
    for key in example_dict:
        if key not in env_dict or not env_dict[key]:
            errors.append(f"Missing required environment variable: '{key}'")

    for key, val in env_dict.items():
        val_lower = val.lower()

        # Check for placeholder passwords in production
        if not allow_placeholders:
            for placeholder in PLACEHOLDER_SUBSTRINGS:
                if placeholder in val_lower:
                    errors.append(f"Insecure placeholder value detected in '{key}': contains '{placeholder}'. Must be rotated for production.")
                    break

        # Check encryption key length
        if key == "N8N_ENCRYPTION_KEY":
            if len(val) < 16:
                errors.append(f"'N8N_ENCRYPTION_KEY' is too short ({len(val)} chars). Minimum 16 characters required for AES security.")

        # Check password strength in production
        if not allow_placeholders and key in PASSWORD_KEYS:
            if len(val) < MIN_PASSWORD_LENGTH:
                errors.append(
                    f"'{key}' is too short ({len(val)} chars). Minimum {MIN_PASSWORD_LENGTH} characters required."
                )

        # Check webhook URL validity
        if key == "WEBHOOK_URL":
            if not val.startswith("http://") and not val.startswith("https://"):
                warnings.append(f"'WEBHOOK_URL' ({val}) does not begin with http:// or https://.")
            elif env_dict.get("NODE_ENV", "").lower() == "production" and val.startswith("http://"):
                warnings.append("'WEBHOOK_URL' uses insecure http:// while NODE_ENV=production. Use https://.")

    if env_dict.get("NODE_ENV", "").lower() == "production":
        if env_dict.get("N8N_PROTOCOL", "").lower() == "http":
            warnings.append("'N8N_PROTOCOL' is set to http in production; https is recommended.")
        if env_dict.get("N8N_BLOCK_ENV_ACCESS_IN_NODE", "true").lower() != "true":
            warnings.append("'N8N_BLOCK_ENV_ACCESS_IN_NODE' should be 'true' in production.")

    return errors, warnings

def main():
    parser = argparse.ArgumentParser(description="Audit .env file for production security readiness.")
    parser.add_argument("--env-file", default=".env", help="Path to target .env file")
    parser.add_argument("--example-file", default=".env.example", help="Path to reference .env.example template")
    parser.add_argument("--allow-placeholders", action="store_true", help="Allow placeholder values (for testing/CI)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit audit results as JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    if not os.path.exists(args.env_file):
        print(f"Error: Target env file '{args.env_file}' does not exist.")
        sys.exit(1)

    if not os.path.exists(args.example_file):
        print(f"Error: Reference example file '{args.example_file}' does not exist.")
        sys.exit(1)

    env_vars = parse_env_file(args.env_file)
    example_vars = parse_env_file(args.example_file)

    errors, warnings = audit_environment(env_vars, example_vars, allow_placeholders=args.allow_placeholders)
    failed = bool(errors) or (args.strict and bool(warnings))

    if args.json_output:
        print(
            json.dumps(
                {
                    "env_file": args.env_file,
                    "example_file": args.example_file,
                    "passed": not failed,
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=2,
            )
        )
        sys.exit(1 if failed else 0)

    print(f"Auditing '{args.env_file}' against '{args.example_file}'...")
    for w in warnings:
        print(f"  [WARN] {w}")
    for e in errors:
        print(f"  [ERROR] {e}")

    print("\n" + "=" * 40)
    print(f"Audit Summary: {len(errors)} error(s), {len(warnings)} warning(s).")
    print("=" * 40)

    if failed:
        print("\nEnvironment audit FAILED. Insecure or missing variables found.")
        sys.exit(1)
    else:
        print("\nEnvironment audit PASSED. Configuration is production ready.")
        sys.exit(0)

if __name__ == "__main__":
    main()
