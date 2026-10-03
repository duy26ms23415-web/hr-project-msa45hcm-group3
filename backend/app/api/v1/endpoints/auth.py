from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token
from app.models.auth import UserAccount, UserRoleAssignment
from app.schemas.auth import LoginRequest, Token, UserResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return access & refresh JWT tokens"""
    stmt = (
        select(UserAccount)
        .where(UserAccount.login_email == login_data.login_email)
        .options(
            selectinload(UserAccount.employee),
            selectinload(UserAccount.role_assignments).selectinload(UserRoleAssignment.role)
        )
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    access_token = create_access_token(subject=user.user_account_id)
    refresh_token = create_refresh_token(subject=user.user_account_id)

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: UserAccount = Depends(get_current_user)):
    """Return profile and active roles of current authenticated user"""
    roles = [ra.role.role_code for ra in current_user.role_assignments]
    return UserResponse(
        user_account_id=current_user.user_account_id,
        employee_id=current_user.employee_id,
        login_email=current_user.login_email,
        is_active=current_user.is_active,
        roles=roles
    )
