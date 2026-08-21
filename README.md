# Production n8n Workflows & GitOps Infrastructure

This repository is a production-ready, GitOps-driven boilerplate for managing self-hosted [n8n](https://n8n.io) integrations and workflows. It demonstrates industry best practices for continuous integration/deployment (CI/CD), security isolation, docker-based scaling (queue mode), and custom workflow validation.

---

## 🏗️ System Architecture

The following diagram illustrates the deployment topology configured in `docker-compose.yml`:

```mermaid
graph TD
    User([External Request / Webhook]) -->|HTTP Port 5678| N8N[n8n App Server]
    N8N -->|Read/Write Data| DB[(PostgreSQL Database)]
    N8N -->|Bull Queue Engine| Redis[(Redis Broker)]
    
    subgraph Operations Container
        Backup[db-backup daemon] -.->|pg_dump hourly| DB
    end
```

---

## 📁 Directory Structure

```text
├── .github/
│   └── workflows/
│       ├── lint-workflows.yml     # CI: Validates JSON structure, naming conventions, & checks secrets
│       └── deploy-workflows.yml   # CD: Deploys workflows to n8n instance via n8n REST API
├── scripts/
│   └── lint_workflows.py          # Custom Python validation script for workflow linting
├── workflows/
│   ├── global_error_handler.json  # Reusable sub-workflow for logging and Slack alerts
│   ├── lead_generation_crm_sync.json # Webhook lead processing & HubSpot CRM integration
│   ├── system_health_check_alerting.json # Automated Cron health checks on APIs and Databases
│   └── automated_invoice_pdf_generator.json # Invoice generation, AWS S3 upload, & email SMTP routing
├── .env.example                   # Environment configuration template
├── docker-compose.yml             # Local production-ready multi-container n8n environment
├── CONTRIBUTING.md                # Developer setup and contribution guidelines
└── LICENSE                        # MIT License
```

---

## 🚀 Getting Started (Local Setup)

### Prerequisites
- Docker & Docker Compose (v2.x or higher)
- Git

### Installation Steps

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/MelvinjoseC/N8N-workflow.git
   cd N8N-workflow
   ```

2. **Configure Environment Variables:**
   Copy the template and fill in your keys:
   ```bash
   cp .env.example .env
   ```
   *Note: Make sure to change values for `N8N_ENCRYPTION_KEY`, database credentials, and API tokens.*

3. **Start the Stack:**
   Initialize all services in detached mode:
   ```bash
   docker compose up -d
   ```
   This will spin up:
   * **n8n app server** listening on `http://localhost:5678`
   * **PostgreSQL 15 database** for workflow storage and execution logs
   * **Redis 7 database** for scale/queue management
   * **Database backup daemon** that automatically takes snapshots and purges backups older than 7 days

4. **Verify Container Health:**
   ```bash
   docker compose ps
   ```

---

## ⚙️ Core Workflows Explained

All workflows in the `workflows/` directory are configured with centralized error routing pointing to the **Global Error Handler** workflow.

### 1. Global Error Handler (`global_error_handler.json`)
* **Trigger:** Error Trigger node.
* **Functionality:** Captures crash/fail execution metadata, formats a clean Slack block message with URLs, and pushes the event to Slack while logging to output.
* **Significance:** Standardizes incident alerts across all integration pipelines.

### 2. Lead Generation & CRM Sync (`lead_generation_crm_sync.json`)
* **Trigger:** Webhook endpoint.
* **Functionality:** Validates and normalizes user input via JS, queries HubSpot by email, forks logic to create or update contact details, and registers a sales notification in Slack.

### 3. System Health Check & Alerting (`system_health_check_alerting.json`)
* **Trigger:** Cron Node (every 15 minutes).
* **Functionality:** Validates external HTTP API connectivity and tests the internal PostgreSQL database latency via `SELECT 1;`. Passes metadata to the evaluator before pushing status reports.

### 4. Automated Invoice PDF Generator (`automated_invoice_pdf_generator.json`)
* **Trigger:** Order confirmation Webhook.
* **Functionality:** Extracts billing records, constructs a responsive HTML invoice template dynamically, sends it to Gotenberg API for PDF generation, uploads the document to Amazon S3, and emails the PDF as an attachment using SMTP.

---

## 🛠️ Tooling & Verification

We support robust local development validation and automated test suites.

### Local CLI Commands (Makefile)
Standardize operations via the included `Makefile`:
- **`make lint`**: Runs custom Python linter over local workflow exports.
- **`make test`**: Runs unit test suite for Python linter and deployment scripts.
- **`make up` / `make down`**: Initialize/shutdown local dockerised stack.
- **`make backup`**: Run Postgres database backup manually.

### Workflow Linting (`scripts/lint_workflows.py`)
Linting rules include:
1. **Secret Scanning:** Scan for hardcoded plaintext credentials (flags base64/hex, allows expressions like `{{ $env.VAR }}`).
2. **Error Handler Check:** Ensure workflows designate an `errorWorkflow` to intercept runtime issues.
3. **Naming Collisions:** Enforce unique, distinct node names.
4. **Disabled Nodes Check:** Warn on nodes left with `"disabled": true` configuration.
5. **Connection Validation:** Verify connections do not reference non-existent source/target node names.
6. **Webhook Auth Warning:** Warn if webhook triggers are fully public without authorization options.

### Unit Test Suites (`tests/`)
We maintain comprehensive unit test coverage for our scripts using `unittest` and `unittest.mock`:
```bash
# Run unit tests locally
python -m unittest discover -s tests
```

---

## 🤖 CI/CD GitOps Pipeline Flow

This repository leverages GitHub Actions to establish robust linting, validation, and deployment pipelines:

### 1. Test & Lint Suite (`run-tests.yml` & `lint-workflows.yml`)
Runs on every Pull Request and Branch Push to execute the python unit tests and run the workflow linter. If tests fail or workflows fail validation, the pipeline is blocked.

### 2. Production CD Sync (`deploy-workflows.yml` -> `scripts/deploy_workflows.py`)
Triggered on merges into `main` or `master` branches targeting workflow file changes. Executes a synchronization script that checks n8n API endpoints, decides whether to execute a `PUT` (for updates) or `POST` (for registering new workflows), and automatically synchronizes git changes to n8n.

