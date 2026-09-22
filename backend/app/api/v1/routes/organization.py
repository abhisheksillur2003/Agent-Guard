from fastapi import APIRouter
from sqlalchemy import select

from backend.app.api.dependencies.auth import CurrentUser, DatabaseSession
from backend.app.core.errors import NotFoundError
from backend.app.models import Organization
from backend.app.schemas.auth import OrganizationResponse

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("", response_model=OrganizationResponse)
async def get_organization(
    user: CurrentUser,
    session: DatabaseSession,
) -> OrganizationResponse:
    organization = await session.scalar(
        select(Organization).where(Organization.id == user.organization_id)
    )
    if organization is None:
        raise NotFoundError("Organization")
    return OrganizationResponse.model_validate(organization)
