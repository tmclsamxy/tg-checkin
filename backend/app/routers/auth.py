"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import User
from ..schemas import ChangePasswordRequest, LoginRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(User).where(User.username == payload.username))
    user = result.scalars().first()

    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message for both cases to avoid user enumeration.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

    return TokenResponse(
        access_token=create_access_token(user.username),
        username=user.username,
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut(username=current_user.username, must_change_password=current_user.must_change_password)


@router.post("/password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前密码不正确")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    await session.commit()
    return {"ok": True, "message": "密码已更新"}
