"""
Authentication service – registration, login, JWT token management.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.hash import argon2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.tenant import Tenant, User
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def register(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        tenant_name: str,
    ) -> TokenResponse:
        # Check existing user
        existing = await self.db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise ValueError("Email already registered")

        # Create tenant
        slug = tenant_name.lower().replace(" ", "-")[:100]
        tenant = Tenant(name=tenant_name, slug=slug)
        self.db.add(tenant)
        await self.db.flush()

        # Create user
        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=argon2.hash(password),
            first_name=first_name,
            last_name=last_name,
            role="owner",
        )
        self.db.add(user)
        await self.db.flush()

        return self._create_tokens(user)

    async def login(self, email: str, password: str) -> TokenResponse | None:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user or not argon2.verify(password, user.password_hash):
            return None

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()

        return self._create_tokens(user)

    async def verify_access_token(self, token: str) -> User | None:
        try:
            # For development, use HS256 with secret_key as fallback
            payload = jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=["HS256"],
            )
            user_id = payload.get("sub")
            if not user_id:
                return None
            result = await self.db.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            )
            return result.scalar_one_or_none()
        except (JWTError, ValueError):
            return None

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse | None:
        try:
            payload = jwt.decode(
                refresh_token,
                self.settings.secret_key,
                algorithms=["HS256"],
            )
            if payload.get("type") != "refresh":
                return None
            user_id = payload.get("sub")
            result = await self.db.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            )
            user = result.scalar_one_or_none()
            if not user:
                return None
            return self._create_tokens(user)
        except (JWTError, ValueError):
            return None

    def _create_tokens(self, user: User) -> TokenResponse:
        now = datetime.now(timezone.utc)

        access_payload = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": user.role,
            "type": "access",
            "exp": now + timedelta(minutes=self.settings.jwt_access_token_expire_minutes),
            "iat": now,
        }
        access_token = jwt.encode(
            access_payload, self.settings.secret_key, algorithm="HS256"
        )

        refresh_payload = {
            "sub": str(user.id),
            "type": "refresh",
            "exp": now + timedelta(days=self.settings.jwt_refresh_token_expire_days),
            "iat": now,
        }
        refresh_token = jwt.encode(
            refresh_payload, self.settings.secret_key, algorithm="HS256"
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.jwt_access_token_expire_minutes * 60,
        )
