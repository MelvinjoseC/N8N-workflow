# Contributing to n8n Workflows Project

Welcome! We are excited that you are interested in contributing to this project. As a team, we follow structured workflows and coding standards to maintain stability and security in our production environments.

---

## 🛠️ Naming Conventions

When creating nodes inside workflows, adhere to the following rules:
- **Unique Names:** Do not use duplicate node names. Referencing node output values using the `$('Node Name')` format depends on names being unique.
- **Descriptive Titles:** Use uppercase letters for custom node titles and prefix them with their main action (e.g., `Fetch Order Details` instead of `HTTP Request`).
- **Trigger Identifiers:** Explicitly state the trigger type and frequency (e.g., `Cron Trigger (15m)`).

---

## 🔐 Credentials & Secrets

- **No Hardcoded Values:** Never commit credentials, tokens, or API keys directly inside workflow JSON templates.
- **Environment Variables:** Reference settings using n8n expressions like `{{ $env.SECRET_VAR }}` or leverage credential managers.
- **Pre-commit Checks:** Run the linter locally before pushing code to catch any potential exposures.

---

## 🌿 Branching Model

We use a simplified Git Flow model for releases:
1. **Branch Naming:**
   - For new integrations: `feature/short-description`
   - For bug fixes: `bugfix/short-description`
   - For system/CI adjustments: `chore/short-description`
2. **Submit PRs:** Create a pull request against the `main` or `master` branch. Ensure the automated lint suite passes.

---

## 📝 Commit Guidelines

We use [Conventional Commits](https://www.conventionalcommits.org/) format to structure our change history:

- **feat:** A new workflow, configuration, or utility script (e.g., `feat: implement lead sync workflow`)
- **fix:** A correction to a node configuration or code block (e.g., `fix: repair webhook path casing`)
- **ci:** Adjustments to pipelines or actions (e.g., `ci: update python runner version`)
- **docs:** Modifications to documentation (e.g., `docs: update readme env values`)

---

## 🧪 Local Testing

Before committing, validate your JSON files using the Python linter:
```bash
python scripts/lint_workflows.py workflows/
```
The pre-merge check will fail if the script returns a non-zero exit code.
