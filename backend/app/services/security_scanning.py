from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models import (
    DetectorKind,
    DetectorStatus,
    DetectorVersion,
    FindingAction,
    FindingSeverity,
    SecurityDetector,
)
from backend.app.schemas.security import (
    DetectorDocument,
    PiiDetectorDocument,
    PromptInjectionDetectorDocument,
    SecretDetectorDocument,
)
from backend.app.services.detectors import detector_document_adapter

MAX_STRING_VALUES = 200
MAX_TOTAL_CHARACTERS = 100_000
MAX_NESTING_DEPTH = 10

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic_api_key": re.compile(
        r"(?:\bsk-[A-Za-z0-9_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
        r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|"
        r"(?i:\b(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?)"
        r"[A-Za-z0-9_./+=-]{12,})"
    ),
}
HIGH_ENTROPY_CANDIDATE = re.compile(r"[A-Za-z0-9+/=_-]{16,}")
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b", re.IGNORECASE),
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)"),
    "credit_card": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
    "ipv4": re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    "india_aadhaar": re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
}
PROMPT_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\bignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|system)\s+instructions?\b",
        re.IGNORECASE,
    ),
    "system_prompt_extraction": re.compile(
        r"\b(?:reveal|show|print|expose|repeat)\b.{0,60}\b(?:system prompt|hidden instructions?)\b",
        re.IGNORECASE,
    ),
    "tool_override": re.compile(
        r"\b(?:bypass|disable|override|evade)\b.{0,60}\b(?:policy|security|guardrails?|tool restrictions?)\b",
        re.IGNORECASE,
    ),
    "role_impersonation": re.compile(
        r"\b(?:you are now|act as|pretend to be)\b.{0,60}\b(?:system|developer|administrator|admin)\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class StringValue:
    location: str
    value: str


@dataclass
class DetectedFinding:
    detector_id: UUID
    detector_version_id: UUID
    detector_kind: DetectorKind
    category: str
    severity: FindingSeverity
    action: FindingAction
    reason_code: str
    location: str
    fingerprint: str
    occurrence_count: int = 1

    def evidence(self) -> dict[str, Any]:
        return {
            "detector_id": str(self.detector_id),
            "detector_version_id": str(self.detector_version_id),
            "kind": self.detector_kind.value,
            "category": self.category,
            "severity": self.severity.value,
            "action": self.action.value,
            "reason_code": self.reason_code,
            "location": self.location,
            "occurrence_count": self.occurrence_count,
        }


@dataclass(frozen=True)
class DetectorEvaluation:
    findings: list[DetectedFinding]
    evaluated_versions: list[dict[str, Any]]


def _safe_path_segment(value: Any) -> str:
    segment = str(value)
    if len(segment) <= 64 and re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        return segment
    digest = hashlib.sha256(segment.encode()).hexdigest()[:12]
    return f"key_{digest}"


def collect_strings(arguments: dict[str, Any]) -> tuple[list[StringValue], bool]:
    values: list[StringValue] = []
    total_characters = 0
    exceeded = False

    def visit(value: Any, location: str, depth: int) -> None:
        nonlocal exceeded, total_characters
        if exceeded:
            return
        if depth > MAX_NESTING_DEPTH:
            exceeded = True
            return
        if isinstance(value, str):
            if (
                len(values) >= MAX_STRING_VALUES
                or total_characters + len(value) > MAX_TOTAL_CHARACTERS
            ):
                exceeded = True
                return
            values.append(StringValue(location=location, value=value))
            total_characters += len(value)
            return
        if isinstance(value, int) and not isinstance(value, bool):
            text = str(value)
            if (
                len(values) >= MAX_STRING_VALUES
                or total_characters + len(text) > MAX_TOTAL_CHARACTERS
            ):
                exceeded = True
                return
            values.append(StringValue(location=location, value=text))
            total_characters += len(text)
            return
        if isinstance(value, dict):
            mapping = cast(dict[Any, Any], value)
            for key, child in mapping.items():
                visit(child, f"{location}.{_safe_path_segment(key)}", depth + 1)
            return
        if isinstance(value, list):
            items = cast(list[Any], value)
            for index, child in enumerate(items):
                visit(child, f"{location}[{index}]", depth + 1)

    visit(arguments, "arguments", 0)
    return values, exceeded


def _fingerprint(category: str, value: str) -> str:
    pepper = get_settings().finding_fingerprint_pepper.get_secret_value().encode()
    return hmac.new(pepper, f"{category}\0{value}".encode(), hashlib.sha256).hexdigest()


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _passes_luhn(value: str) -> bool:
    digits = [int(character) for character in value if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _scope_matches(
    document: DetectorDocument,
    *,
    agent_id: UUID,
    tool_id: UUID,
    operation: str,
    environment: str,
) -> bool:
    scope = document.scope
    return (
        (not scope.agent_ids or agent_id in scope.agent_ids)
        and (not scope.tool_ids or tool_id in scope.tool_ids)
        and (not scope.operations or operation in scope.operations)
        and (not scope.environments or environment in scope.environments)
    )


def _new_finding(
    detector: SecurityDetector,
    version: DetectorVersion,
    document: DetectorDocument,
    category: str,
    location: str,
    matched_value: str,
) -> DetectedFinding:
    return DetectedFinding(
        detector_id=detector.id,
        detector_version_id=version.id,
        detector_kind=document.kind,
        category=category,
        severity=document.severity,
        action=document.action,
        reason_code=document.reason_code,
        location=location,
        fingerprint=_fingerprint(category, matched_value),
    )


def _scan_secrets(
    detector: SecurityDetector,
    version: DetectorVersion,
    document: SecretDetectorDocument,
    values: list[StringValue],
) -> list[DetectedFinding]:
    findings: list[DetectedFinding] = []
    for item in values:
        for secret_type in document.secret_types:
            if secret_type == "high_entropy":
                for match in HIGH_ENTROPY_CANDIDATE.finditer(item.value):
                    candidate = match.group(0)
                    if (
                        len(candidate) >= document.minimum_token_length
                        and _entropy(candidate) >= document.minimum_entropy
                    ):
                        findings.append(
                            _new_finding(
                                detector,
                                version,
                                document,
                                secret_type,
                                item.location,
                                candidate,
                            )
                        )
                continue
            for match in SECRET_PATTERNS[secret_type].finditer(item.value):
                findings.append(
                    _new_finding(
                        detector,
                        version,
                        document,
                        secret_type,
                        item.location,
                        match.group(0),
                    )
                )
    return findings


def _scan_pii(
    detector: SecurityDetector,
    version: DetectorVersion,
    document: PiiDetectorDocument,
    values: list[StringValue],
) -> list[DetectedFinding]:
    findings: list[DetectedFinding] = []
    for item in values:
        for entity in document.entities:
            for match in PII_PATTERNS[entity].finditer(item.value):
                candidate = match.group(0)
                if entity == "credit_card" and not _passes_luhn(candidate):
                    continue
                if entity == "ipv4":
                    try:
                        ipaddress.IPv4Address(candidate)
                    except ipaddress.AddressValueError:
                        continue
                findings.append(
                    _new_finding(
                        detector,
                        version,
                        document,
                        entity,
                        item.location,
                        candidate,
                    )
                )
    return findings


def _scan_prompt_injection(
    detector: SecurityDetector,
    version: DetectorVersion,
    document: PromptInjectionDetectorDocument,
    values: list[StringValue],
) -> list[DetectedFinding]:
    findings: list[DetectedFinding] = []
    for item in values:
        normalized = re.sub(r"\s+", " ", item.value)
        for rule in document.rules:
            for match in PROMPT_PATTERNS[rule].finditer(normalized):
                findings.append(
                    _new_finding(
                        detector,
                        version,
                        document,
                        rule,
                        item.location,
                        match.group(0),
                    )
                )
    return findings


def _deduplicate(findings: list[DetectedFinding]) -> list[DetectedFinding]:
    unique: dict[tuple[UUID, str, str, str], DetectedFinding] = {}
    for finding in findings:
        key = (
            finding.detector_version_id,
            finding.category,
            finding.location,
            finding.fingerprint,
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = finding
        else:
            existing.occurrence_count += finding.occurrence_count
    return list(unique.values())


async def active_detector_rows(
    session: AsyncSession, organization_id: UUID
) -> list[tuple[SecurityDetector, DetectorVersion]]:
    rows = (
        await session.execute(
            select(SecurityDetector, DetectorVersion)
            .join(
                DetectorVersion,
                (DetectorVersion.detector_id == SecurityDetector.id)
                & (DetectorVersion.version == SecurityDetector.current_version),
            )
            .where(
                SecurityDetector.organization_id == organization_id,
                SecurityDetector.status == DetectorStatus.ACTIVE,
            )
            .order_by(SecurityDetector.priority, SecurityDetector.id)
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


def detector_version_evidence(
    rows: list[tuple[SecurityDetector, DetectorVersion]],
) -> list[dict[str, Any]]:
    return [
        {
            "detector_id": str(detector.id),
            "detector_version_id": str(version.id),
            "version": version.version,
        }
        for detector, version in rows
    ]


async def evaluate_security_detectors(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    operation: str,
    environment: str,
    arguments: dict[str, Any],
) -> DetectorEvaluation:
    rows = await active_detector_rows(session, organization_id)
    evaluated_versions = detector_version_evidence(rows)
    string_values, scan_limit_exceeded = collect_strings(arguments)
    findings: list[DetectedFinding] = []
    for detector, version in rows:
        try:
            document = detector_document_adapter.validate_python(version.document_json)
        except PydanticValidationError:
            findings.append(
                DetectedFinding(
                    detector_id=detector.id,
                    detector_version_id=version.id,
                    detector_kind=DetectorKind.SECRET,
                    category="detector_configuration_invalid",
                    severity=FindingSeverity.CRITICAL,
                    action=FindingAction.DENY,
                    reason_code="DETECTOR_CONFIGURATION_INVALID",
                    location="detector_configuration",
                    fingerprint=_fingerprint(
                        "detector_configuration_invalid", f"{detector.id}:{version.version}"
                    ),
                )
            )
            continue
        if not _scope_matches(
            document,
            agent_id=agent_id,
            tool_id=tool_id,
            operation=operation,
            environment=environment,
        ):
            continue
        if scan_limit_exceeded:
            findings.append(
                DetectedFinding(
                    detector_id=detector.id,
                    detector_version_id=version.id,
                    detector_kind=document.kind,
                    category="scan_limit_exceeded",
                    severity=FindingSeverity.CRITICAL,
                    action=FindingAction.DENY,
                    reason_code="SECURITY_SCAN_LIMIT_EXCEEDED",
                    location="arguments",
                    fingerprint=_fingerprint("scan_limit_exceeded", str(version.id)),
                )
            )
            break
        if isinstance(document, SecretDetectorDocument):
            findings.extend(_scan_secrets(detector, version, document, string_values))
        elif isinstance(document, PiiDetectorDocument):
            findings.extend(_scan_pii(detector, version, document, string_values))
        else:
            findings.extend(_scan_prompt_injection(detector, version, document, string_values))
    return DetectorEvaluation(
        findings=_deduplicate(findings),
        evaluated_versions=evaluated_versions,
    )
