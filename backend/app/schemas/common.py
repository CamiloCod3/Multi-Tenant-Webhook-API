from typing import List, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIMessage(BaseModel):
    detail: str


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    items: List[T]