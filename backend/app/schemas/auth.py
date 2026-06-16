# backend/app/schemas/auth.py
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    tenant_id: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginIn(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=1)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class WhoAmIOut(BaseModel):
    tenant_id: str
    email: EmailStr
    role: str
    created_at: datetime