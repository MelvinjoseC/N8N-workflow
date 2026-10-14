# ADR 0002: Scaling n8n with Redis Bull Queue Mode

## Status
Accepted

## Context
Default n8n installations operate in `EXECUTIONS_MODE=regular`, where webhook ingestion, UI serving, cron scheduling, and workflow executions all share a single Node.js process. Under high webhook concurrency or heavy memory-intensive tasks (e.g. PDF generation, large data transforms), the event loop blocks, resulting in HTTP 504 gateway timeouts and dropped triggers.

## Decision
We configure Redis 7 with Bull Queue backend in `docker-compose.yml` and provide seamless scalability:
1. **Primary Instance (Webhook / Webhook Processor):** Receives incoming traffic, runs cron schedules, and serves UI.
2. **Execution Broker (Redis 7):** Buffers incoming execution jobs in Redis lists with persistence.
3. **Worker Instances (`EXECUTIONS_MODE=queue`):** Dedicated worker nodes consume jobs from Redis, executing CPU and I/O intensive nodes independently without choking the web server.

## Consequences
- **Positive:** High availability, zero dropped webhooks during load spikes, and linear horizontal scalability.
- **Negative:** Increased infrastructure footprint (requires Redis container and worker orchestrations).
