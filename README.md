# Multi-Tenant Webhook API

A production-style **FastAPI backend** for multi-tenant webhook ingestion, contact/event tracking, message logging, operational metrics, and secure event processing.

This project was built as a practical backend and DevOps portfolio project. It demonstrates how to design a service that can receive external events from automation platforms, CRMs, internal tools, or other systems while keeping tenant data isolated and operationally observable.

---

## What This Project Demonstrates

- Multi-tenant backend design
- Secure webhook ingestion with HMAC or token-based authentication
- Idempotent event processing
- Contact/entity upsert logic
- Message and event lifecycle tracking
- Failed event storage and retry workflow
- PostgreSQL data modeling with SQLAlchemy
- Alembic database migrations
- Redis-backed rate limiting and operational support
- Prometheus metrics endpoint
- Health, liveness, and readiness checks
- Dockerized application deployment
- Production-oriented deployment workflow with rollback logic

---

## Tech Stack

| Area | Tools |
|---|---|
| Backend | FastAPI, Pydantic 2 |
| Database | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| Cache / Rate Limiting | Redis 7 |
| Infrastructure | Docker, Docker Compose |
| CI/CD | GitHub Actions, GHCR |
| Observability | Prometheus metrics, structured logging, Sentry support |
| Security | HMAC verification, admin token auth, security headers, trusted hosts, CORS controls |

---

## Quick Start

```bash
# Start local development stack
cd infra
docker-compose up -d

# Run database migrations
docker-compose exec api alembic upgrade head

# Test health endpoint
curl http://localhost:8000/api/v1/healthz
```

> Note: add a safe `.env` file or use `.env.example` once available. Never commit real secrets.

---

## API Overview

| Area | Prefix | Auth | Purpose |
|---|---|---|---|
| Health | `/api/v1/healthz`, `/api/v1/livez`, `/api/v1/readyz` | None | Runtime and dependency checks |
| Tenants | `/api/v1/tenants` | Admin Token | Tenant management and tenant-level stats |
| Webhooks | `/api/v1/webhooks/lead-event` | HMAC or Token URL | External event ingestion |
| Contacts | `/api/v1/tenants/{id}/contacts` | Admin Token | Contact/entity search, updates, opt-out handling |
| Messages | `/api/v1/tenants/{id}/message-logs` | Admin Token | Message lifecycle logging and filtering |
| Failed Events | `/api/v1/tenants/{id}/failed-events` | Admin Token | Dead-letter queue, retry, cleanup |
| Metrics | `/api/v1/metrics/overview` | Admin Token | Application KPIs |
| Prometheus | `/metrics` | Metrics Token | Prometheus scrape endpoint |

Full endpoint documentation with request/response examples: **[API_DOCS.md](API_DOCS.md)**

---

## Architecture

```text
External Systems / Automation Platforms / CRMs
        |
        v  signed webhook event
   ┌────────────┐     ┌──────────────┐     ┌──────────┐
   │  FastAPI   │────>│  PostgreSQL  │     │  Redis   │
   │  Backend   │     │  Database    │     │ Rate Lim │
   └────────────┘     └──────────────┘     └──────────┘
        |
        v
Webhook Event → Validation → Idempotency Check → Contact/Entity Upsert → Stats → Logs → Metrics
```

---

## Event Ingestion Flow

Each webhook event can trigger a structured processing pipeline:

1. Validate authentication and request metadata
2. Store the event idempotently
3. Normalize event type aliases
4. Upsert the related contact/entity record
5. Update status progression without moving backward
6. Update campaign/workflow-style aggregate stats where applicable
7. Create message lifecycle logs for relevant events
8. Handle opt-out events
9. Store failed events for later retry

This makes the project useful as a generic foundation for CRM integrations, automation workflows, messaging systems, or event-driven backend services.

---

## Multi-Tenancy

The application uses row-based tenant isolation through `tenant_id` across tenant-owned tables. Each tenant can receive a unique webhook URL for event ingestion. Tenant deletion cascades through related data to keep cleanup predictable.

---

## Security Features

- HMAC-SHA256 webhook verification
- Token-based webhook fallback for tenant-specific URLs
- Admin token protection for management endpoints
- Metrics token protection for Prometheus scraping
- Production secret validation
- Trusted host configuration
- CORS configuration
- Request correlation IDs
- Security headers including CSP, HSTS, frame protection, no-sniff, and no-store caching
- Rate limiting support

---

## Project Structure

```text
backend/
  app/
    core/        # Config, DB, logging, security, rate limiting, audit helpers
    models/      # SQLAlchemy models
    routers/     # API endpoints
    schemas/     # Pydantic validation models
    services/    # Event ingestion and business logic
  alembic/       # Database migrations
infra/
  docker-compose.prod.yml
  deploy_prod.sh
```

---

## Deployment Notes

The repository includes a production-oriented deployment setup using Docker images, GitHub Actions, GHCR, and a remote Linux server.

The deployment script demonstrates:

- environment validation
- GHCR login
- Docker image pull
- Redis service startup
- Alembic migrations before container replacement
- health checks after deployment
- automatic rollback to the last successful image tag
- Docker image cleanup

For a public portfolio version, production deployment should be treated as an example workflow and adapted to your own environment.

---

## Migrations

```bash
# Show current migration version
docker-compose exec api alembic current

# Apply pending migrations
docker-compose exec api alembic upgrade head

# Roll back one migration
docker-compose exec api alembic downgrade -1
```

---

## What I Learned

This project helped me practice real-world backend and infrastructure concepts, including:

- designing tenant-aware APIs
- handling external webhooks securely
- structuring FastAPI applications with routers, services, schemas, and models
- working with PostgreSQL migrations
- using Redis in backend infrastructure
- building Docker-based deployment flows
- thinking about production readiness, observability, and rollback safety

---

## Future Improvements

- Add automated test coverage for core flows
- Replace simple admin token auth with RBAC/JWT-based administration
- Add OpenTelemetry tracing
- Add background workers for async event processing
- Add local development Docker Compose file if separate from production
- Add Kubernetes or Docker Swarm deployment example
- Improve API examples and demo seed data

---

## License

Apache License 2.0
