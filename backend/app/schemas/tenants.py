# backend/app/schemas/tenants.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .base import ORMBaseModel


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    plan: str = Field(default="basic", max_length=50)


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    plan: Optional[str] = Field(default=None, max_length=50)


class TenantOut(ORMBaseModel):
    id: str
    name: str
    plan: str
    created_at: datetime

    webhook_url: str
    dashboard_url: str
