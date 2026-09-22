from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import ConflictError, NotFoundError, ValidationError
from backend.app.models import ActorType, Agent, DetectorVersion, SecurityDetector, Tool
from backend.app.schemas.security import (
    DetectorCreate,
    DetectorDocument,
    DetectorResponse,
    DetectorUpdate,
    DetectorVersionResponse,
)
from backend.app.services.audit import record_audit

detector_document_adapter: TypeAdapter[DetectorDocument] = TypeAdapter(DetectorDocument)


async def _validate_scope(
    session: AsyncSession, organization_id: UUID, document: DetectorDocument
) -> None:
    if document.scope.agent_ids:
        count = await session.scalar(
            select(func.count())
            .select_from(Agent)
            .where(
                Agent.organization_id == organization_id,
                Agent.id.in_(document.scope.agent_ids),
            )
        )
        if count != len(document.scope.agent_ids):
            raise ValidationError("Every scoped agent must belong to the organization")
    if document.scope.tool_ids:
        count = await session.scalar(
            select(func.count())
            .select_from(Tool)
            .where(
                Tool.organization_id == organization_id,
                Tool.id.in_(document.scope.tool_ids),
            )
        )
        if count != len(document.scope.tool_ids):
            raise ValidationError("Every scoped tool must belong to the organization")


async def get_detector(
    session: AsyncSession, organization_id: UUID, detector_id: UUID
) -> SecurityDetector:
    detector = await session.scalar(
        select(SecurityDetector).where(
            SecurityDetector.id == detector_id,
            SecurityDetector.organization_id == organization_id,
        )
    )
    if detector is None:
        raise NotFoundError("Security detector")
    return detector


async def get_detector_version(
    session: AsyncSession, detector_id: UUID, version: int
) -> DetectorVersion:
    detector_version = await session.scalar(
        select(DetectorVersion).where(
            DetectorVersion.detector_id == detector_id,
            DetectorVersion.version == version,
        )
    )
    if detector_version is None:
        raise NotFoundError("Detector version")
    return detector_version


async def list_detectors(session: AsyncSession, organization_id: UUID) -> list[SecurityDetector]:
    result = await session.scalars(
        select(SecurityDetector)
        .where(SecurityDetector.organization_id == organization_id)
        .order_by(SecurityDetector.priority, SecurityDetector.name, SecurityDetector.id)
    )
    return list(result.all())


async def list_detector_versions(session: AsyncSession, detector_id: UUID) -> list[DetectorVersion]:
    result = await session.scalars(
        select(DetectorVersion)
        .where(DetectorVersion.detector_id == detector_id)
        .order_by(DetectorVersion.version.desc())
    )
    return list(result.all())


def version_response(version: DetectorVersion) -> DetectorVersionResponse:
    return DetectorVersionResponse(
        id=version.id,
        detector_id=version.detector_id,
        version=version.version,
        document=detector_document_adapter.validate_python(version.document_json),
        created_by=version.created_by,
        created_at=version.created_at,
    )


async def detector_response(session: AsyncSession, detector: SecurityDetector) -> DetectorResponse:
    current = await get_detector_version(session, detector.id, detector.current_version)
    return DetectorResponse(
        id=detector.id,
        organization_id=detector.organization_id,
        name=detector.name,
        description=detector.description,
        status=detector.status,
        priority=detector.priority,
        current_version=detector.current_version,
        document=detector_document_adapter.validate_python(current.document_json),
        created_by=detector.created_by,
        created_at=detector.created_at,
        updated_at=detector.updated_at,
    )


async def create_detector(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    data: DetectorCreate,
    request_id: str | None,
) -> SecurityDetector:
    duplicate = await session.scalar(
        select(SecurityDetector.id).where(
            SecurityDetector.organization_id == organization_id,
            SecurityDetector.name == data.name,
        )
    )
    if duplicate is not None:
        raise ConflictError("A security detector with this name already exists")
    await _validate_scope(session, organization_id, data.document)
    detector = SecurityDetector(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        priority=data.priority,
        current_version=1,
        created_by=actor_id,
    )
    session.add(detector)
    await session.flush()
    version = DetectorVersion(
        detector_id=detector.id,
        version=1,
        document_json=data.document.model_dump(mode="json"),
        created_by=actor_id,
    )
    session.add(version)
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="detector.create",
        target_type="security_detector",
        target_id=detector.id,
        after={
            "name": detector.name,
            "status": detector.status,
            "priority": detector.priority,
            "version": 1,
            "document": version.document_json,
        },
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(detector)
    return detector


async def update_detector(
    session: AsyncSession,
    *,
    organization_id: UUID,
    detector_id: UUID,
    actor_id: UUID,
    data: DetectorUpdate,
    request_id: str | None,
) -> SecurityDetector:
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("At least one detector field must be provided")
    detector = await get_detector(session, organization_id, detector_id)
    before = {
        "name": detector.name,
        "description": detector.description,
        "status": detector.status,
        "priority": detector.priority,
        "version": detector.current_version,
    }
    if data.name is not None and data.name != detector.name:
        normalized_name = data.name.strip()
        duplicate = await session.scalar(
            select(SecurityDetector.id).where(
                SecurityDetector.organization_id == organization_id,
                SecurityDetector.name == normalized_name,
                SecurityDetector.id != detector.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("A security detector with this name already exists")
        detector.name = normalized_name
    if "description" in changes:
        detector.description = data.description
    if data.priority is not None:
        detector.priority = data.priority
    if data.status is not None:
        detector.status = data.status
    if data.document is not None:
        await _validate_scope(session, organization_id, data.document)
        detector.current_version += 1
        session.add(
            DetectorVersion(
                detector_id=detector.id,
                version=detector.current_version,
                document_json=data.document.model_dump(mode="json"),
                created_by=actor_id,
            )
        )
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="detector.update",
        target_type="security_detector",
        target_id=detector.id,
        before=before,
        after={
            "name": detector.name,
            "description": detector.description,
            "status": detector.status,
            "priority": detector.priority,
            "version": detector.current_version,
        },
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(detector)
    return detector
