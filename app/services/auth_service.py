from __future__ import annotations
import jwt
import bcrypt
from typing import Optional, Dict, Any,List
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from pydantic import BaseModel, EmailStr, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.utils.logger import get_loggers
from app.models.auth import User
import asyncio
from functools import partial

logger = get_loggers("AuthService")


class TokenData(BaseModel):
    user_id: str
    tenant_id: str
    email: EmailStr
    scopes: List[str] = []
    token_type: str = "access_token"


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                partial(
                    bcrypt.checkpw,
                    plain_password.encode('utf-8'),
                    hashed_password.encode('utf-8')
                )
            )
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False

    async def get_password_hash(self, password: str) -> str:

        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        loop = asyncio.get_event_loop()
        hashed = await loop.run_in_executor(
            None,
            partial(bcrypt.hashpw, password.encode('utf-8'), bcrypt.gensalt())
        )
        return hashed.decode('utf-8')

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        try:
            to_encode = data.copy()
            now = datetime.now(timezone.utc)

            if expires_delta:
                expire = now + expires_delta
            else:
                expire = now + \
                    timedelta(minutes=self.access_token_expire_minutes)

            to_encode.update({
                "exp": expire,
                "iat": now,
                "nbf": now,
                "type": "access_token",
                "jti": f"{data.get('user_id')}_{int(now.timestamp())}"
            })

            encoded_jwt = jwt.encode(
                to_encode, self.secret_key, algorithm=self.algorithm)
            logger.info(
                f"Access token created for user: {data.get('user_id')}")
            return encoded_jwt

        except Exception as e:
            logger.error(f"Token creation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create access token"
            )

    def create_refresh_token(self, data: dict) -> str:
        to_encode = data.copy()
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=30)

        to_encode.update({
            "exp": expire,
            "iat": now,
            "type": "refresh_token",
            "jti": f"{data.get('user_id')}_refresh_{int(now.timestamp())}"
        })

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    async def verify_token(self, token: str, expected_type: str = "access_token") -> Optional[TokenData]:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": True}
            )

            if payload.get("type") != expected_type:
                logger.warning(f"Invalid token type: {payload.get('type')}")
                return None

            required_fields = ["user_id", "tenant_id", "email", "exp"]
            if not all(k in payload for k in required_fields):
                logger.warning("Invalid token structure")
                return None

            user = await self._get_user_by_id(payload["user_id"])
            if not user or not user.is_active:
                logger.warning(
                    f"User inactive or deleted: {payload['user_id']}")
                return None

            return TokenData(
                user_id=payload["user_id"],
                tenant_id=payload["tenant_id"],
                email=payload["email"],
                scopes=payload.get("scopes", []),
                token_type=payload.get("type", "access_token")
            )

        except jwt.ExpiredSignatureError:
            logger.warning("Token signature expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None

    async def _get_user_by_id(self, user_id: str) -> Optional[User]:
        try:
            result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Database error fetching user: {e}")
            return None

    async def _get_user_by_email(self, email: str) -> Optional[User]:
        try:
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Database error fetching user: {e}")
            return None

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        try:

            user = await self._get_user_by_email(email)

            if not user:
                logger.warning(f"User not found: {email}")

                await asyncio.sleep(0.5)
                return None

            if not await self.verify_password(password, user.hashed_password):
                logger.warning(f"Invalid password for user: {email}")

                await asyncio.sleep(0.5)
                return None

            if not user.is_active:
                logger.warning(f"Inactive user attempted login: {email}")
                return None

            user.last_login = datetime.now(timezone.utc)
            await self.db.commit()

            logger.info(f"User authenticated successfully: {email}")
            return {
                "user_id": str(user.id),
                "tenant_id": str(user.tenant_id),
                "email": user.email,
                "scopes": user.scopes or []
            }

        except Exception as e:
            logger.error(f"Authentication error for {email}: {e}")
            await self.db.rollback()
            return None

    async def create_user(self, email: str, password: str, tenant_id: str, **kwargs) -> User:
        try:

            existing_user = await self._get_user_by_email(email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email already exists"
                )

            hashed_password = await self.get_password_hash(password)

            user = User(
                email=email,
                hashed_password=hashed_password,
                tenant_id=tenant_id,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                **kwargs
            )

            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

            logger.info(f"User created: {email}")
            return user

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"User creation failed: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create user"
            )

    async def revoke_token(self, token_jti: str):

        pass
