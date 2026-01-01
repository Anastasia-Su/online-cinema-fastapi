from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class CommentCreateSchema(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_id: Optional[int] = Field(None, description="For replies")
    
    @field_validator("parent_id", mode="before")
    @classmethod
    def normalize_parent_id(cls, v):
        if v in (None, "", 0):
            return None
        return v


class CommentUpdateSchema(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class CommentLikeSchema(BaseModel):
    liked: bool = True


class CommentBaseSchema(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: datetime
    user_id: int
    movie_id: int
    parent_id: Optional[int] = None

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class CommentSchema(CommentBaseSchema):
    username: str
    like_count: int
    user_has_liked: bool = False
    replies: list["CommentSchema"] = []


CommentSchema.model_rebuild()
