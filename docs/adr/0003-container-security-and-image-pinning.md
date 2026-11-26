# 0003: Container Security Hardening and Image Pinning

## Status

Accepted

## Context

Running container images with `:latest` tags introduces non-deterministic upgrades and makes rollbacks unreliable. Additionally, binding internal helper services (such as Gotenberg) to `0.0.0.0` exposes unauthenticated internal APIs on host network interfaces, and running containers with default Linux privileges increases the blast radius of any container escape.

## Decision

1. **Configurable Image Pinning:** Pin `n8nio/n8n` and `gotenberg/gotenberg` to explicit version tags in `docker-compose.yml` (`N8N_IMAGE_TAG` and `GOTENBERG_IMAGE_TAG` with tested defaults).
2. **Localhost Port Binding:** Bind `gotenberg` to `127.0.0.1:3000:3000` and `n8n` to `${N8N_BIND_ADDR:-127.0.0.1}:${N8N_PORT:-5678}:5678` so production traffic must pass through a TLS-terminating reverse proxy.
3. **Privilege Dropping:** Apply `security_opt: ["no-new-privileges:true"]` across all services (`postgres`, `redis`, `gotenberg`, `n8n`, `n8n-worker`, `db-backup`).
4. **Telemetry & Pruning:** Disable n8n diagnostics/personalization telemetry and enable automatic execution log pruning (`EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=336`).

## Consequences

- Upgrades require explicit version bumps in `.env` or `docker-compose.yml`, ensuring repeatable deployments.
- Production deployments behind Nginx/Traefik/Caddy work securely out of the box without exposing internal ports to the public internet.
