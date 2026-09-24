# Phase 8: observability

Phase 8 adds operational visibility without moving security decisions out of the deterministic control plane. Metrics and traces contain bounded operational metadata only. They never include credentials, raw tool arguments, finding evidence, policy documents, user email addresses, tenant IDs, agent IDs, tool IDs, or approval reasons.

## Signals

The API exposes Prometheus metrics at `GET /metrics`:

- request rate, status class, in-flight requests, and duration by normalized route template;
- durable policy decisions by outcome;
- durable security findings by fixed detector kind, severity, and action;
- completed approval transitions by status; and
- controlled execution attempts by terminal status.

Resource IDs and raw paths are excluded from metric labels to keep cardinality bounded. The `/metrics` scrape itself is not counted.

HTTP requests produce OpenTelemetry server spans. Span attributes are limited to the normalized route, HTTP method, and response status. Incoming W3C trace context is preserved, JSON logs include the active trace and span IDs, and each response includes `x-trace-id` for support correlation. Celery maintenance tasks also create spans with only a record count.

## Local stack

The `observability` Docker Compose profile runs:

- OpenTelemetry Collector for OTLP ingestion and batching;
- Tempo for local trace storage and search;
- Prometheus for metric collection and seven-day local retention; and
- Grafana with provisioned Prometheus and Tempo data sources plus an AgentGuard overview dashboard.

All published monitoring ports bind to `127.0.0.1`. Anonymous Grafana access is read-only and intended only for this local profile.

Start the stack with:

```powershell
docker compose --profile observability up -d
```

Set `AGENTGUARD_OTEL_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces` before starting FastAPI. Prometheus scrapes the host API on port 8000. Open Grafana at `http://127.0.0.1:3001`, Prometheus at `http://127.0.0.1:9090`, and Tempo at `http://127.0.0.1:3200`.

## Completion criteria

Phase 8 is complete when metrics use bounded labels, trace propagation and log correlation pass automated tests, the Compose configuration validates, Prometheus reports the API target as healthy, Tempo receives API spans, the provisioned Grafana dashboard loads, and the full backend and frontend verification suites pass.
