# Multi-Tenant Webhook API Documentation

**Version:** 0.4.0  
**Example Base URL:** `https://api.example.com`

This document describes the public API surface for a generic multi-tenant webhook ingestion backend. All domains, tenants, contacts, and payloads shown here are safe examples.

---

## Authentication

All management endpoints, except health checks and webhook ingestion, require an admin token header:

```http
X-Admin-Token: <your-admin-token>
```

Webhook endpoints support either:

- HMAC-SHA256 request signing
- tenant-specific tokenized webhook URLs

Prometheus metrics are protected in production with:

```http
X-Metrics-Token: <your-metrics-token>
```

---

## Health

### GET /api/v1/healthz

Basic liveness check. Returns 200 if the process is running.

**Auth:** None

```json
{"ok": true}
```

### GET /api/v1/livez

Liveness probe. Functionally equivalent to `/healthz`.

**Auth:** None

### GET /api/v1/readyz

Readiness check. Verifies required dependencies such as database and Redis connectivity.

**Auth:** None

```json
{
  "ok": true,
  "checks": {
    "database": "healthy",
    "redis": "healthy"
  }
}
```

---

## Tenants

Tenant endpoints are used to manage isolated customer/workspace accounts.

### POST /api/v1/tenants

Creates a new tenant and returns a unique tokenized webhook URL.

**Auth:** `X-Admin-Token`

```json
{
  "name": "Acme Demo Workspace",
  "plan": "basic"
}
```

**Response:**

```json
{
  "id": "uuid",
  "name": "Acme Demo Workspace",
  "plan": "basic",
  "created_at": "2026-03-15T12:00:00Z",
  "webhook_url": "https://api.example.com/api/v1/webhooks/lead-event/t/<token>"
}
```

### GET /api/v1/tenants

Lists all tenants.

**Auth:** `X-Admin-Token`

### GET /api/v1/tenants/{tenant_id}

Returns a single tenant.

**Auth:** `X-Admin-Token`

### PATCH /api/v1/tenants/{tenant_id}

Updates tenant metadata.

**Auth:** `X-Admin-Token`

```json
{
  "name": "Updated Demo Workspace",
  "plan": "pro"
}
```

### DELETE /api/v1/tenants/{tenant_id}

Deletes a tenant and its related data according to configured database cascade rules.

**Auth:** `X-Admin-Token`

---

## Webhooks

Webhook endpoints receive signed or token-authenticated external events from automation tools, CRMs, internal systems, or other applications.

### POST /api/v1/webhooks/lead-event

Ingests an external event with HMAC signature verification.

**Auth:** HMAC-SHA256 signature

Required headers:

```http
X-Signature: <hmac-hex-digest>
X-Timestamp: <unix-timestamp>
X-Tenant-ID: <tenant-id>
```

Signature format:

```text
HMAC-SHA256(secret, "<timestamp>.<raw-body>")
```

Example body:

```json
{
  "tenant_id": "uuid",
  "lead_id": "entity-123",
  "event_id": "evt-001",
  "event_type": "lead_created",
  "source": "automation-platform",
  "timestamp": "2026-03-15T12:00:00Z",
  "data": {
    "campaign_id": "campaign-1",
    "campaign_name": "Demo Campaign",
    "first_name": "Alex",
    "last_name": "Morgan",
    "email": "alex@example.com",
    "phone": "+46700000000"
  }
}
```

**Response:**

```json
{"detail": "Lead event ingested (corr=<request-id>)"}
```

Duplicate events are ignored idempotently:

```json
{"detail": "Duplicate event ignored (event_id=evt-001, corr=<request-id>)"}
```

### POST /api/v1/webhooks/lead-event/t/{token}

Token-based webhook endpoint. The token identifies the tenant, so `tenant_id` can be omitted from the request body.

**Auth:** Token in URL

### Supported Event Types

Events are normalized internally. The current implementation supports lifecycle-style lead/contact, messaging, workflow, conversion, and opt-out events.

| Category | Accepted values | Canonical |
|---|---|---|
| Entity created | `lead.created`, `lead_created`, `created` | `lead_created` |
| Entity imported | `lead.imported`, `imported` | `lead_imported` |
| Contacted | `contacted` | `contacted` |
| Email sent | `email.sent`, `email_sent` | `email_sent` |
| SMS sent | `sms.sent`, `sms_sent` | `sms_sent` |
| Email delivered | `email.delivered`, `delivered` | `email_delivered` |
| SMS delivered | `sms.delivered`, `sms_delivered` | `sms_delivered` |
| Engaged | `engaged` | `engaged` |
| Email opened | `email.opened`, `opened`, `open` | `email_opened` |
| Link clicked | `clicked`, `click`, `link.clicked` | `clicked` |
| Replied | `replied`, `reply` | `replied` |
| Email bounced | `email.bounced`, `bounced`, `bounce` | `email_bounced` |
| SMS failed | `sms.failed`, `sms_failed` | `sms_failed` |
| Email failed | `email.failed`, `email_failed` | `email_failed` |
| Converted | `converted`, `convert` | `converted` |
| Deal won | `deal.won`, `deal_won`, `won` | `deal_won` |
| Sale | `sale` | `sale` |
| Workflow processed | `workflow.processed` | `workflow_processed` |
| Workflow success | `workflow.success`, `success` | `workflow_success` |
| Workflow failed | `workflow.failed` | `workflow_failed` |
| Opt-out all | `opt_out`, `unsubscribe`, `opt.out` | `opt_out_all` |
| Opt-out SMS | `opt_out_sms`, `stop`, `sms.opt_out` | `opt_out_sms` |
| Opt-out email | `opt_out_email`, `email.unsubscribe` | `opt_out_email` |

### Ingestion Pipeline

Each accepted event can trigger the following processing flow:

1. Store the event idempotently by `event_id`
2. Upsert the related contact/entity record
3. Update lifecycle status without moving backward
4. Update campaign/workflow-style aggregate statistics when present
5. Update revenue/conversion snapshots when present
6. Create message logs for email/SMS lifecycle events
7. Handle opt-out events
8. Store failures in the dead-letter queue for retry

### Timestamp Aliases

If `timestamp` is missing, the system falls back to `occurred_at` or `created_at`.

### Data Packing

If `data` is empty or missing, non-standard top-level fields are packed into `data` automatically.

---

## Contacts

All contact endpoints are scoped to a tenant:

```text
/api/v1/tenants/{tenant_id}/contacts
```

### GET /api/v1/tenants/{tenant_id}/contacts

Lists contacts with filtering and search.

**Auth:** `X-Admin-Token`

| Param | Type | Description |
|---|---|---|
| status | string | Filter by lifecycle status |
| source | string | Filter by source system |
| is_member | bool | Filter by membership flag |
| opted_out | bool | `true` = only opt-outs, `false` = only active contacts |
| search | string | Free text search over name, email, or phone |
| limit | int | 1-500, default 50 |
| offset | int | default 0 |

### GET /api/v1/tenants/{tenant_id}/contacts/count

Returns contact count, optionally filtered by status.

**Auth:** `X-Admin-Token`

```json
{"tenant_id": "uuid", "total": 42, "status_filter": null}
```

### GET /api/v1/tenants/{tenant_id}/contacts/{contact_id}

Returns full contact details.

**Auth:** `X-Admin-Token`

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "external_contact_id": "entity-123",
  "first_name": "Alex",
  "last_name": "Morgan",
  "email": "alex@example.com",
  "phone": "+46700000000",
  "normalized_phone": "+46700000000",
  "registration_number": null,
  "source": "automation-platform",
  "status": "converted",
  "member_status": "non_member",
  "is_member": false,
  "opted_out_sms": false,
  "opted_out_email": false,
  "opt_out_reason": null,
  "opted_out_at": null,
  "consent_sms": false,
  "consent_email": false,
  "tags": [],
  "metadata_json": {},
  "last_message_sent_at": "2026-03-15T12:01:00Z",
  "last_engagement_at": "2026-03-15T12:02:00Z",
  "last_seen_at": "2026-03-15T12:02:00Z",
  "created_at": "2026-03-15T12:00:00Z",
  "updated_at": "2026-03-15T12:02:00Z"
}
```

### POST /api/v1/tenants/{tenant_id}/contacts

Creates a contact manually.

**Auth:** `X-Admin-Token`

```json
{
  "first_name": "Jamie",
  "last_name": "Taylor",
  "email": "jamie@example.com",
  "phone": "+46700000001",
  "source": "api",
  "status": "new"
}
```

**Errors:** `409` if email or phone already exists for the tenant.

### PATCH /api/v1/tenants/{tenant_id}/contacts/{contact_id}

Partially updates a contact. Only included fields are changed.

**Auth:** `X-Admin-Token`

```json
{
  "first_name": "Jamie A.",
  "status": "contacted"
}
```

### POST /api/v1/tenants/{tenant_id}/contacts/{contact_id}/opt-out

Opts out a contact from a channel.

**Auth:** `X-Admin-Token`

```json
{
  "channel": "sms",
  "source": "user_reply",
  "reason": "User requested unsubscribe"
}
```

`channel`: `sms`, `email`, or `all`

### POST /api/v1/tenants/{tenant_id}/contacts/{contact_id}/opt-in

Reverses an opt-out.

**Auth:** `X-Admin-Token`

```json
{
  "channel": "sms",
  "source": "admin_action"
}
```

### GET /api/v1/tenants/{tenant_id}/contacts/{contact_id}/opt-out-events

Returns opt-out history for a contact.

**Auth:** `X-Admin-Token`

Query params: `limit`, `offset`

---

## Message Logs

All message log endpoints are scoped to:

```text
/api/v1/tenants/{tenant_id}/message-logs
```

### POST /api/v1/tenants/{tenant_id}/message-logs

Logs a sent or received message manually. The related contact must already exist.

**Auth:** `X-Admin-Token`

```json
{
  "contact_id": "uuid",
  "channel": "sms",
  "direction": "outbound",
  "provider": "example-provider",
  "provider_message_id": "ext-msg-123",
  "body": "This is a safe demo message.",
  "status": "sent"
}
```

`channel`: `sms` or `email`  
`direction`: `outbound` or `inbound`  
`status`: `queued`, `sent`, `delivered`, `failed`, `opened`, `clicked`, `replied`, `bounced`

### GET /api/v1/tenants/{tenant_id}/message-logs

Lists message logs with filters.

**Auth:** `X-Admin-Token`

| Param | Type | Description |
|---|---|---|
| contact_id | string | Filter by contact |
| campaign_id | string | Filter by campaign |
| workflow_id | string | Filter by workflow |
| channel | string | `sms` or `email` |
| direction | string | `outbound` or `inbound` |
| status | string | Filter by status |
| limit | int | 1-500, default 50 |
| offset | int | default 0 |

### GET /api/v1/tenants/{tenant_id}/message-logs/{message_id}

Returns a single message log.

**Auth:** `X-Admin-Token`

---

## Failed Events / Dead Letter Queue

All endpoints are scoped to:

```text
/api/v1/tenants/{tenant_id}/failed-events
```

### GET /api/v1/tenants/{tenant_id}/failed-events

Lists failed events, newest first.

**Auth:** `X-Admin-Token`

Query params: `limit`, `offset`

### GET /api/v1/tenants/{tenant_id}/failed-events/count

Returns the number of failed events.

**Auth:** `X-Admin-Token`

### GET /api/v1/tenants/{tenant_id}/failed-events/{id}

Returns a single failed event with full payload.

**Auth:** `X-Admin-Token`

### POST /api/v1/tenants/{tenant_id}/failed-events/{id}/retry

Re-processes a failed event. On success, it is removed from the queue. On failure, `retry_count` is incremented.

**Auth:** `X-Admin-Token`

### DELETE /api/v1/tenants/{tenant_id}/failed-events/{id}

Permanently removes a failed event from the queue.

**Auth:** `X-Admin-Token`

---

## Metrics

### GET /api/v1/metrics/overview

Returns dashboard-style overview metrics.

**Auth:** `X-Admin-Token`

Query params: `tenant_id` optional. Omit for global overview.

```json
{
  "tenant_id": "uuid",
  "total_campaigns": 3,
  "total_workflows": 2,
  "total_lead_events": 150,
  "total_revenue": "45000.00",
  "currency": "SEK",
  "total_contacts": 42,
  "contact_status_breakdown": {
    "new": 10,
    "contacted": 15,
    "engaged": 12,
    "converted": 5,
    "other": 0
  },
  "total_opted_out_sms": 3,
  "total_opted_out_email": 1,
  "total_messages": 89,
  "total_messages_sent": 45,
  "total_messages_delivered": 40,
  "total_messages_failed": 2,
  "total_failed_events": 0,
  "last_event_at": "2026-03-15T14:30:00Z",
  "last_revenue_snapshot_at": "2026-03-15T14:00:00Z"
}
```

### GET /api/v1/metrics/campaigns

Lists campaign-style statistics.

**Auth:** `X-Admin-Token`

Query params: `tenant_id`, `limit`, `offset`

### GET /api/v1/metrics/workflows

Lists workflow statistics.

**Auth:** `X-Admin-Token`

Query params: `tenant_id`, `limit`, `offset`

### GET /api/v1/metrics/lead-events

Lists raw ingested events.

**Auth:** `X-Admin-Token`

Query params: `tenant_id`, `event_type`, `limit`, `offset`

### GET /api/v1/metrics/revenue

Lists conversion/revenue snapshots.

**Auth:** `X-Admin-Token`

Query params: `tenant_id`, `limit`, `offset`

### Tenant-Scoped Metric Endpoints

These endpoints provide tenant-filtered views:

- `GET /api/v1/tenants/{tenant_id}/campaign-stats`
- `GET /api/v1/tenants/{tenant_id}/workflow-stats`
- `GET /api/v1/tenants/{tenant_id}/lead-events`
- `GET /api/v1/tenants/{tenant_id}/revenue-snapshots`

---

## Prometheus Metrics

### GET /metrics

Prometheus-compatible metrics endpoint.

**Auth:** `X-Metrics-Token` header in production

---

## Error Responses

All errors follow the same general format:

```json
{
  "detail": "Error message",
  "request_id": "uuid"
}
```

| Code | Meaning |
|---|---|
| 401 | Missing or invalid authentication |
| 404 | Resource not found |
| 409 | Conflict, such as duplicate email or phone |
| 413 | Payload too large |
| 422 | Validation error |
| 429 | Rate limited |
| 500 | Internal server error |

---

## Rate Limits

| Endpoint group | Limit |
|---|---|
| Health checks | 100/min default |
| Tenant CRUD | 10-30/min |
| Webhooks | 60/min |
| Contacts read | 60/min |
| Contacts write | 30/min |
| Message logs read | 60/min |
| Message logs write | 120/min |
| Metrics overview | 30/min |
| Metrics lists | 60/min |
| Failed events | 60/min |
| Failed events retry/delete | 10/min |
| Auth register | 5/min |

Rate limiting is per tenant when `X-Tenant-ID` or JWT tenant context is available, with IP fallback.
