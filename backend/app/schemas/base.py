# app/schemas/base.py
from pydantic import BaseModel, ConfigDict


class ORMBaseModel(BaseModel):
    """
    Basmodell för alla scheman som mappas från SQLAlchemy-ORM.
    Använder Pydantic v2 from_attributes istället för orm_mode.
    """
    model_config = ConfigDict(from_attributes=True)
