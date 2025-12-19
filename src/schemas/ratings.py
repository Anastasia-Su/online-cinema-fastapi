# src/schemas/ratings.py
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class RatingBase(BaseModel):
    rating: int = Field(..., ge=1, le=10, description="Rating from 1 to 10")


class RatingCreateSchema(RatingBase):
    pass


class RatingUpdateSchema(RatingBase):
    pass  


class RatingSchema(RatingBase):
    user_id: int
    movie_id: int
    created_at: datetime
    updated_at: datetime

    username: Optional[str] = None
    
    model_config: ConfigDict = ConfigDict(from_attributes=True)
