from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from backend.app.api.dependencies.auth import CurrentAgent, CurrentUser, DatabaseSession
from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.schemas.agents import AgentPrincipalResponse
from backend.app.schemas.auth import CurrentUserResponse, TokenResponse
from backend.app.services.authentication import authenticate_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DatabaseSession,
) -> TokenResponse:
    user = await authenticate_user(session, form.username, form.password)
    token = create_access_token(user.id, user.organization_id, str(user.role))
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().access_token_minutes * 60,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)


@router.get("/agent/me", response_model=AgentPrincipalResponse)
async def current_agent(agent: CurrentAgent) -> AgentPrincipalResponse:
    return AgentPrincipalResponse.model_validate(agent)
