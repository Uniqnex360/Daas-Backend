from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional,List
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.services.auth_service import AuthService, TokenData
from app.database import get_db
from app.utils.logger import get_loggers
logger = get_loggers("Dependencies")
security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    scopes: List[str]

    class Config:
        frozen = True


async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    auth_service: AuthService = Depends(get_auth_service),
) -> CurrentUser:
    request_id = getattr(request.state, "request_id", "unknown")
    if not credentials:
        logger.warning(f"[{request_id}] Missing authentication credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token_data = await auth_service.verify_token(
            credentials.credentials,
            expected_type="access_token"
        )
    except Exception as e:
        logger.error(f"[{request_id}] Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not token_data:
        logger.warning(f"[{request_id}] Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if x_tenant_id and token_data.tenant_id != x_tenant_id:
        logger.warning(
            f"[{request_id}] User {token_data.user_id} attempted access to tenant {x_tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this tenant is forbidden"
        )
    logger.debug(
        f"[{request_id}] User authenticated: {token_data.user_id} "
        f"for tenant: {token_data.tenant_id}"
    )
    return CurrentUser(
        user_id=token_data.user_id,
        tenant_id=token_data.tenant_id,
        email=token_data.email,
        scopes=token_data.scopes
    )


async def get_current_active_user(
    current_user: CurrentUser = Depends(get_current_user)
) -> CurrentUser:
    return current_user


async def get_current_tenant(
    current_user: CurrentUser = Depends(get_current_user)
) -> str:
    if not current_user.tenant_id:
        logger.error("User missing tenant_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User tenant information missing"
        )
    return current_user.tenant_id


def require_scope(required_scope: str):
    async def scope_dependency(
        current_user: CurrentUser = Depends(get_current_user)
    ):
        if required_scope not in current_user.scopes:
            logger.warning(
                f"User {current_user.user_id} missing required scope: {required_scope}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: {required_scope}"
            )
        return current_user
    return scope_dependency


def require_scopes(required_scopes: List[str], require_all: bool = True):
    async def scope_dependency(
        current_user: CurrentUser = Depends(get_current_user)
    ):
        user_scopes = set(current_user.scopes)
        required = set(required_scopes)
        if require_all:
            has_access = required.issubset(user_scopes)
            error_msg = f"Missing required scopes: {required - user_scopes}"
        else:
            has_access = bool(required.intersection(user_scopes))
            error_msg = f"Must have at least one of: {required_scopes}"
        if not has_access:
            logger.warning(
                f"User {current_user.user_id} failed scope check: {error_msg}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. {error_msg}"
            )
        return current_user
    return scope_dependency


def require_admin(
    current_user: CurrentUser = Depends(get_current_user)
):
    if "admin" not in current_user.scopes:
        logger.warning(
            f"User {current_user.user_id} attempted admin-only action"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


require_read = require_scope("read")
require_write = require_scope("write")
require_delete = require_scope("delete")
