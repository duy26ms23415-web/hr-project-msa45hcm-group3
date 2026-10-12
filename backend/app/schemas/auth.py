from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class LoginRequest(BaseModel):
    login_email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    type: Optional[str] = None


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    role_code: str
    role_name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_account_id: int
    employee_id: int
    login_email: str
    is_active: bool
    roles: List[str] = []
