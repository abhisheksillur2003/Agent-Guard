from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import (
    DetectorKind,
    FindingAction,
    FindingSeverity,
    User,
    UserRole,
)
from backend.app.schemas.security import (
    DetectorCreate,
    DetectorResponse,
    DetectorUpdate,
    DetectorVersionResponse,
    SecurityFindingResponse,
)
from backend.app.services import detectors as detector_service
from backend.app.services import findings as finding_service

router = APIRouter(prefix="/security", tags=["security"])
SecurityViewer = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.DEVELOPER,
            UserRole.APPROVER,
            UserRole.READ_ONLY,
        )
    ),
]
Administrator = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.post("/detectors", response_model=DetectorResponse, status_code=status.HTTP_201_CREATED)
async def create_detector(
    data: DetectorCreate,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> DetectorResponse:
    detector = await detector_service.create_detector(
        session,
        organization_id=user.organization_id,
        actor_id=user.id,
        data=data,
        request_id=get_request_id(request),
    )
    return await detector_service.detector_response(session, detector)


@router.get("/detectors", response_model=list[DetectorResponse])
async def list_detectors(
    user: SecurityViewer,
    session: DatabaseSession,
) -> list[DetectorResponse]:
    detectors = await detector_service.list_detectors(session, user.organization_id)
    return [await detector_service.detector_response(session, detector) for detector in detectors]


@router.get("/detectors/{detector_id}", response_model=DetectorResponse)
async def get_detector(
    detector_id: UUID,
    user: SecurityViewer,
    session: DatabaseSession,
) -> DetectorResponse:
    detector = await detector_service.get_detector(session, user.organization_id, detector_id)
    return await detector_service.detector_response(session, detector)


@router.patch("/detectors/{detector_id}", response_model=DetectorResponse)
async def update_detector(
    detector_id: UUID,
    data: DetectorUpdate,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> DetectorResponse:
    detector = await detector_service.update_detector(
        session,
        organization_id=user.organization_id,
        detector_id=detector_id,
        actor_id=user.id,
        data=data,
        request_id=get_request_id(request),
    )
    return await detector_service.detector_response(session, detector)


@router.get(
    "/detectors/{detector_id}/versions",
    response_model=list[DetectorVersionResponse],
)
async def list_detector_versions(
    detector_id: UUID,
    user: SecurityViewer,
    session: DatabaseSession,
) -> list[DetectorVersionResponse]:
    detector = await detector_service.get_detector(session, user.organization_id, detector_id)
    versions = await detector_service.list_detector_versions(session, detector.id)
    return [detector_service.version_response(version) for version in versions]


@router.get("/findings", response_model=list[SecurityFindingResponse])
async def list_findings(
    user: SecurityViewer,
    session: DatabaseSession,
    decision_id: Annotated[UUID | None, Query()] = None,
    detector_kind: Annotated[DetectorKind | None, Query()] = None,
    severity: Annotated[FindingSeverity | None, Query()] = None,
    action: Annotated[FindingAction | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[SecurityFindingResponse]:
    findings = await finding_service.list_findings(
        session,
        user.organization_id,
        decision_id=decision_id,
        detector_kind=detector_kind,
        severity=severity,
        action=action,
        limit=limit,
    )
    return [SecurityFindingResponse.model_validate(finding) for finding in findings]


@router.get("/findings/{finding_id}", response_model=SecurityFindingResponse)
async def get_finding(
    finding_id: UUID,
    user: SecurityViewer,
    session: DatabaseSession,
) -> SecurityFindingResponse:
    finding = await finding_service.get_finding(session, user.organization_id, finding_id)
    return SecurityFindingResponse.model_validate(finding)
