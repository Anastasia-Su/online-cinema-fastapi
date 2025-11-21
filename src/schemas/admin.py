# src/schemas/admin.py
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    field_serializer,
    Field,
    computed_field,
)
from src.database import UserGroupEnum, UserGroupModel
from typing import Optional
from datetime import datetime


class UserGroupUpdateSchema(BaseModel):
    group: UserGroupEnum


class UserListSchema(BaseModel):
    id: int
    email: EmailStr
    group: UserGroupEnum = Field(alias="group_name")
    is_active: bool

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class UserDetailSchema(UserListSchema):
    created_at: str = Field(alias="created")
    updated_at: str = Field(alias="updated")
    model_config = ConfigDict(from_attributes=True)


class UserActivateSchema(BaseModel):
    is_active: bool
