from fastapi import APIRouter

from backend.app.api.v1.routes import (
    agents,
    approvals,
    audit,
    auth,
    executions,
    local_ai,
    organization,
    permissions,
    policies,
    security,
    tool_requests,
    tools,
    users,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(organization.router)
router.include_router(users.router)
router.include_router(agents.router)
router.include_router(approvals.router)
router.include_router(tools.router)
router.include_router(permissions.router)
router.include_router(policies.router)
router.include_router(security.router)
router.include_router(tool_requests.router)
router.include_router(executions.router)
router.include_router(local_ai.router)
router.include_router(audit.router)
