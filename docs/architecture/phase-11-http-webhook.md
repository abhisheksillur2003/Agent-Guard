# Phase 11: guarded HTTP webhook connector

Phase 11 adds `http_webhook@1`, the first adapter that can produce a real external side effect. It preserves the existing execution boundary: the adapter is reachable only after AgentGuard authenticates the agent, validates the registered JSON schema, confirms permission, scans content, evaluates deterministic policy, completes any required approval, checks reliability limits, and durably records authorization.

## Request contract

Register webhook tools with `write` and `external_egress` capabilities. The recommended input schema is:

```json
{
  "type": "object",
  "properties": {
    "url": { "type": "string", "format": "uri" },
    "payload": {}
  },
  "required": ["url", "payload"],
  "additionalProperties": false
}
```

Every execution must contain exactly `url` and `payload`. The URL must exactly match a configured allowlist entry. Put secrets in the runtime bearer-token map; do not place credentials in the URL, query string, tool schema, payload, database, or policy.

The outbound request contains JSON plus these controlled headers:

- `Authorization: Bearer ...` when a token exists for the exact URL.
- `Idempotency-Key` using the stable AgentGuard execution ID.
- `X-AgentGuard-Execution-ID` and `X-AgentGuard-Decision-ID` for correlation.
- `User-Agent` with the AgentGuard version.

The adapter does not automatically retry. A webhook is a side-effecting operation and an idempotency header cannot prove that every receiver deduplicates correctly.

## Network controls

- The connector is disabled unless explicitly enabled.
- Destinations use an exact URL allowlist; redirects, embedded credentials, query strings, and fragments are rejected.
- Production destinations must use HTTPS.
- DNS is resolved before the request, non-global addresses are denied by default, and the connection is pinned to the vetted address while TLS still verifies the original hostname.
- HTTP environment proxies are ignored.
- Responses are read only up to the configured byte limit.
- Response bodies are discarded. AgentGuard stores status, media type, byte count, and SHA-256 only.
- Failures use bounded machine-readable codes without storing upstream exception text.

`AGENTGUARD_HTTP_WEBHOOK_ALLOW_PRIVATE_NETWORKS=true` relaxes the address check for an intentionally trusted internal endpoint. Treat this as a high-impact network permission and keep the exact URL allowlist narrow.

## Windows local testing

When FastAPI runs directly from PowerShell and the test receiver runs on Windows, a local configuration can use:

```dotenv
AGENTGUARD_HTTP_WEBHOOK_ENABLED=true
AGENTGUARD_HTTP_WEBHOOK_ALLOWED_URLS=["http://127.0.0.1:8081/agentguard"]
AGENTGUARD_HTTP_WEBHOOK_BEARER_TOKENS={}
AGENTGUARD_HTTP_WEBHOOK_ALLOW_PRIVATE_NETWORKS=true
```

When FastAPI runs inside Docker Desktop, use an exact `host.docker.internal` URL instead of `127.0.0.1`. HTTP is accepted only outside production. Restart the API after changing `.env`, then confirm the adapter is marked **configured** on the Tools page.

## Failure codes

| Code                                  | Meaning                                                        |
| ------------------------------------- | -------------------------------------------------------------- |
| `HTTP_WEBHOOK_DISABLED`               | Runtime configuration has not enabled the adapter.             |
| `HTTP_WEBHOOK_ARGUMENTS_INVALID`      | Arguments or destination URL violate the connector contract.   |
| `HTTP_WEBHOOK_URL_NOT_ALLOWED`        | The exact destination is absent from the allowlist.            |
| `HTTP_WEBHOOK_HTTPS_REQUIRED`         | A production destination attempted plain HTTP.                 |
| `HTTP_WEBHOOK_DNS_FAILED`             | The destination could not be resolved safely.                  |
| `HTTP_WEBHOOK_PRIVATE_NETWORK_DENIED` | DNS returned a private or otherwise non-global address.        |
| `HTTP_WEBHOOK_UPSTREAM_REJECTED`      | The receiver returned a non-2xx response, including redirects. |
| `HTTP_WEBHOOK_RESPONSE_TOO_LARGE`     | The response exceeded the configured limit.                    |
| `HTTP_WEBHOOK_REQUEST_FAILED`         | The outbound connection failed.                                |
