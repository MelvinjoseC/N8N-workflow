# Security Policy

## Supported Versions

We actively support and fix security issues in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| Main branch | :white_check_mark: |
| < 1.0.0 | :x:                |

## Reporting a Vulnerability

We take the security of our workflows and infrastructure configurations seriously. If you find a security vulnerability, please do **not** open a public issue on GitHub. Instead, report it privately:

1. Email your findings to `security@example.com`.
2. Include details on the vulnerability, steps to reproduce, and potential impact.
3. We will acknowledge receipt of your report within 48 hours and work with you on a coordinated disclosure plan.

## Hardening Recommendations

This repository provides production-hardened boilerplate. Ensure you enforce the following in production:
- Replace all placeholder values in `.env` with strong, randomly generated keys.
- Do not expose port `5678` directly to the internet; always route traffic through a secure reverse proxy (e.g., Traefik, Nginx) with SSL/TLS termination.
- Set `N8N_BASIC_AUTH_ACTIVE=true` (or use active OAuth2/SAML credentials integrations) to secure the dashboard.
- Set `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` to prevent unauthorized workflow scripts from reading host/container environment variables.
