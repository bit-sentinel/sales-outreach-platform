"""Authentication endpoints – register, login, refresh, logout."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.hash import argon2
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import APIResponse
from app.services.auth_service import AuthService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/register", response_model=APIResponse[TokenResponse], status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    auth = AuthService(db)
    result = await auth.register(
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        tenant_name=body.tenant_name,
    )
    return APIResponse(data=result)


@router.post("/login", response_model=APIResponse[TokenResponse])
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from app.models.tenant import User
    from sqlalchemy import select as _select
    auth = AuthService(db)
    result = await auth.login(email=body.email, password=body.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Log login event with IP + user agent
    try:
        user_row = (await db.execute(_select(User).where(User.email == body.email))).scalar_one_or_none()
        if user_row:
            from app.api.audit import log_action
            ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
            ua = request.headers.get("User-Agent", "")[:500]
            await log_action(
                db,
                tenant_id=user_row.tenant_id,
                user_id=user_row.id,
                action="user.login",
                resource_type="user",
                resource_id=str(user_row.id),
                details={"email": body.email, "ip": ip, "user_agent": ua},
            )
            await db.commit()
    except Exception:
        pass  # never block login over audit failure

    return APIResponse(data=result)


@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh_token(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    auth = AuthService(db)
    result = await auth.refresh_tokens(body.refresh_token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    return APIResponse(data=result)


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_me(current_user=Depends(get_current_user)):
    return APIResponse(data=UserResponse.model_validate(current_user))


@router.patch("/me", response_model=APIResponse[UserResponse])
async def update_profile(
    body: ProfileUpdateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.first_name = body.first_name
    current_user.last_name = body.last_name
    await db.commit()
    await db.refresh(current_user)
    return APIResponse(data=UserResponse.model_validate(current_user))


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not argon2.verify(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = argon2.hash(body.new_password)
    await db.commit()
    return APIResponse(message="Password updated successfully")


@router.post("/logout")
async def logout(current_user=Depends(get_current_user)):
    # Token revocation handled by removing refresh token on client
    return APIResponse(message="Logged out successfully")
