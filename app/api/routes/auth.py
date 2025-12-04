from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from app.database import get_db, get_redis
from app.services.auth_service import AuthService
from app.api.dependencies import get_current_user, get_auth_service, CurrentUser
from app.utils.logger import get_loggers
from app.config import settings
import time

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_loggers("AuthRoutes")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserInfo"


class UserInfo(BaseModel):
    user_id: str
    email: EmailStr
    tenant_id: str
    scopes: List[str]


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LoginAuditLog(BaseModel):
    user_id: str
    ip_address: str
    user_agent: str
    success: bool
    timestamp: float


async def check_login_rate_limit(
    username: str,
    ip_address: str,
    redis_client=None
) -> None:

    if not redis_client:
        return

    ip_key = f"login_attempts:ip:{ip_address}"
    ip_attempts = await redis_client.incr(ip_key)
    if ip_attempts == 1:
        await redis_client.expire(ip_key, 60)

    if ip_attempts > 5:
        logger.warning(f"Rate limit exceeded for IP: {ip_address}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": "60"}
        )

    user_key = f"login_attempts:user:{username}"
    user_attempts = await redis_client.incr(user_key)
    if user_attempts == 1:
        await redis_client.expire(user_key, 300)

    if user_attempts > 3:
        logger.warning(f"Rate limit exceeded for user: {username}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in 5 minutes.",
            headers={"Retry-After": "300"}
        )


async def record_failed_login(username: str, redis_client=None):
    if not redis_client:
        return

    logger.warning(f"Failed login attempt for: {username}")


async def clear_login_attempts(username: str, redis_client=None):
    if not redis_client:
        return

    user_key = f"login_attempts:user:{username}"
    await redis_client.delete(user_key)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    redis_client=Depends(get_redis)
):

    client_ip = request.headers.get(
        "X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")

    try:

        await check_login_rate_limit(form_data.username, client_ip, redis_client)

        user = await auth_service.authenticate_user(form_data.username, form_data.password)

        if not user:

            await record_failed_login(form_data.username, redis_client)

            background_tasks.add_task(
                log_login_audit,
                LoginAuditLog(
                    user_id="unknown",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    success=False,
                    timestamp=time.time()
                ),
                db
            )

            logger.warning(
                f"Failed login attempt | User: {form_data.username} | IP: {client_ip}")

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        await clear_login_attempts(form_data.username, redis_client)

        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={
                "user_id": user["user_id"],
                "tenant_id": user["tenant_id"],
                "email": user["email"],
                "scopes": user["scopes"]
            },
            expires_delta=access_token_expires
        )

        refresh_token = auth_service.create_refresh_token(
            data={
                "user_id": user["user_id"],
                "tenant_id": user["tenant_id"],
                "email": user["email"],
            }
        )

        logger.info(
            f"Successful login | User: {user['email']} | IP: {client_ip}")

        background_tasks.add_task(
            log_login_audit,
            LoginAuditLog(
                user_id=user["user_id"],
                ip_address=client_ip,
                user_agent=user_agent,
                success=True,
                timestamp=time.time()
            ),
            db
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserInfo(
                user_id=user["user_id"],
                email=user["email"],
                tenant_id=user["tenant_id"],
                scopes=user["scopes"]
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Login error | User: {form_data.username} | Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service temporarily unavailable"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):

    try:

        token_data = await auth_service.verify_token(
            refresh_request.refresh_token,
            expected_type="refresh_token"
        )

        if not token_data:
            logger.warning("Invalid refresh token attempted")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={
                "user_id": token_data.user_id,
                "tenant_id": token_data.tenant_id,
                "email": token_data.email,
                "scopes": token_data.scopes
            },
            expires_delta=access_token_expires
        )

        new_refresh_token = auth_service.create_refresh_token(
            data={
                "user_id": token_data.user_id,
                "tenant_id": token_data.tenant_id,
                "email": token_data.email,
            }
        )

        logger.info(f"Token refreshed | User: {token_data.email}")

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserInfo(
                user_id=token_data.user_id,
                email=token_data.email,
                tenant_id=token_data.tenant_id,
                scopes=token_data.scopes
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not refresh token"
        )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: CurrentUser = Depends(get_current_user)
):
    return UserInfo(
        user_id=current_user.user_id,
        email=current_user.email,
        tenant_id=current_user.tenant_id,
        scopes=current_user.scopes
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis)
):

    try:

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

            import jwt
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.ALGORITHM],
                    options={"verify_exp": False}
                )
                jti = payload.get("jti")
                exp = payload.get("exp")

                if jti and redis_client:

                    ttl = max(1, int(exp - time.time()))
                    await redis_client.setex(f"blacklist:{jti}", ttl, "1")
                    logger.info(
                        f"Token blacklisted | User: {current_user.email} | JTI: {jti}")

            except Exception as e:
                logger.error(f"Error blacklisting token: {e}")

        client_ip = request.headers.get(
            "X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        background_tasks.add_task(
            log_logout_audit,
            current_user.user_id,
            client_ip,
            db
        )

        logger.info(
            f"User logged out | User: {current_user.email} | IP: {client_ip}")

        return {
            "message": "Successfully logged out",
            "detail": "Token has been revoked"
        }

    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)

        return {"message": "Logged out"}


async def log_login_audit(audit_log: LoginAuditLog, db: AsyncSession):

    try:

        logger.info(
            f"Login audit | "
            f"User: {audit_log.user_id} | "
            f"IP: {audit_log.ip_address} | "
            f"Success: {audit_log.success} | "
            f"UserAgent: {audit_log.user_agent[:50]}"
        )
    except Exception as e:
        logger.error(f"Failed to save login audit: {e}")


async def log_logout_audit(user_id: str, ip_address: str, db: AsyncSession):

    try:

        logger.info(f"Logout audit | User: {user_id} | IP: {ip_address}")
    except Exception as e:
        logger.error(f"Failed to save logout audit: {e}")
