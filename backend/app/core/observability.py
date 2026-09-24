from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from enum import StrEnum
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

if TYPE_CHECKING:
    from backend.app.core.config import Settings
    from backend.app.services.security_scanning import DetectedFinding


HTTP_REQUESTS = Counter(
    "agentguard_http_requests_total",
    "HTTP requests handled by the AgentGuard API.",
    ("method", "route", "status_class"),
)
HTTP_DURATION = Histogram(
    "agentguard_http_request_duration_seconds",
    "AgentGuard API request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_IN_PROGRESS = Gauge(
    "agentguard_http_requests_in_progress",
    "HTTP requests currently executing in the AgentGuard API.",
)
POLICY_DECISIONS = Counter(
    "agentguard_policy_decisions_total",
    "Durably recorded policy gateway decisions.",
    ("outcome",),
)
SECURITY_FINDINGS = Counter(
    "agentguard_security_findings_total",
    "Durably recorded deterministic security findings.",
    ("kind", "severity", "action"),
)
APPROVAL_TRANSITIONS = Counter(
    "agentguard_approval_transitions_total",
    "Completed approval state transitions.",
    ("status",),
)
EXECUTION_ATTEMPTS = Counter(
    "agentguard_execution_attempts_total",
    "Completed controlled tool execution attempts.",
    ("status",),
)

_provider: TracerProvider | None = None
_known_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


def _label(value: StrEnum | str) -> str:
    return value.value if isinstance(value, StrEnum) else value


def configure_tracing(settings: Settings) -> Tracer:
    """Configure one process-local provider without exporting request content."""
    global _provider
    if _provider is None:
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": settings.service_version,
                "deployment.environment.name": settings.environment,
            }
        )
        provider = TracerProvider(resource=resource)
        if settings.otel_traces_endpoint:
            exporter = OTLPSpanExporter(endpoint=settings.otel_traces_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
    return trace.get_tracer("agentguard", settings.service_version)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def install_observability(application: FastAPI, settings: Settings) -> None:
    tracer = configure_tracing(settings)

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.middleware("http")
    async def observe_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        started = time.perf_counter()
        status_code = 500
        HTTP_IN_PROGRESS.inc()
        parent_context = propagate.extract(dict(request.headers))
        with tracer.start_as_current_span(
            "HTTP request",
            context=parent_context,
            kind=SpanKind.SERVER,
        ) as span:
            try:
                response = await call_next(request)
                status_code = response.status_code
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                route = _route_template(request)
                raw_method = request.method.upper()
                method = raw_method if raw_method in _known_methods else "OTHER"
                elapsed = time.perf_counter() - started
                span.update_name(f"{method} {route}")
                span.set_attribute("http.request.method", method)
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status_code)
                HTTP_IN_PROGRESS.dec()
                HTTP_REQUESTS.labels(method, route, f"{status_code // 100}xx").inc()
                HTTP_DURATION.labels(method, route).observe(elapsed)
            span_context = span.get_span_context()
            if span_context.is_valid:
                response.headers["x-trace-id"] = format(span_context.trace_id, "032x")
            return response


def record_policy_decision(
    outcome: StrEnum | str,
    findings: Iterable[DetectedFinding] = (),
) -> None:
    POLICY_DECISIONS.labels(_label(outcome)).inc()
    for finding in findings:
        SECURITY_FINDINGS.labels(
            _label(finding.detector_kind),
            _label(finding.severity),
            _label(finding.action),
        ).inc()


def record_approval_transition(status: StrEnum | str, amount: int = 1) -> None:
    if amount > 0:
        APPROVAL_TRANSITIONS.labels(_label(status)).inc(amount)


def record_execution_attempt(status: StrEnum | str) -> None:
    EXECUTION_ATTEMPTS.labels(_label(status)).inc()
