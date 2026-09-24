import json
import logging
from uuid import uuid4

import httpx

from backend.app.core.config import get_settings
from backend.app.core.logging import JsonFormatter
from backend.app.core.observability import (
    configure_tracing,
    record_approval_transition,
    record_execution_attempt,
    record_policy_decision,
)
from backend.app.main import app
from backend.app.models import ApprovalStatus, DecisionOutcome, ExecutionStatus


async def test_metrics_expose_bounded_route_labels_without_resource_ids() -> None:
    resource_id = str(uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(f"/api/v1/agents/{resource_id}")
        unsupported = await client.request("X-CUSTOM", "/healthz")
        metrics = await client.get("/metrics")

    assert denied.status_code == 401
    assert unsupported.status_code == 405
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "agentguard_http_requests_total" in metrics.text
    assert 'route="/agents/{agent_id}"' in metrics.text
    assert 'route="/metrics"' not in metrics.text
    assert 'method="OTHER",route="/healthz"' in metrics.text
    assert "X-CUSTOM" not in metrics.text
    assert resource_id not in metrics.text


async def test_trace_context_is_preserved_without_recording_request_content() -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    traceparent = f"00-{trace_id}-0123456789abcdef-01"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz", headers={"traceparent": traceparent})

    assert response.status_code == 200
    assert response.headers["x-trace-id"] == trace_id


async def test_domain_metrics_use_fixed_security_outcome_labels() -> None:
    record_policy_decision(DecisionOutcome.DENY)
    record_approval_transition(ApprovalStatus.REJECTED)
    record_execution_attempt(ExecutionStatus.SUCCEEDED)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        metrics = await client.get("/metrics")

    assert 'agentguard_policy_decisions_total{outcome="deny"}' in metrics.text
    assert 'agentguard_approval_transitions_total{status="rejected"}' in metrics.text
    assert 'agentguard_execution_attempts_total{status="succeeded"}' in metrics.text


def test_json_logs_include_trace_correlation_only_when_a_span_is_active() -> None:
    formatter = JsonFormatter()
    tracer = configure_tracing(get_settings())
    record = logging.LogRecord(
        name="agentguard.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="safe event",
        args=(),
        exc_info=None,
    )

    with tracer.start_as_current_span("test-span"):
        payload = json.loads(formatter.format(record))

    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16
    assert payload["message"] == "safe event"
