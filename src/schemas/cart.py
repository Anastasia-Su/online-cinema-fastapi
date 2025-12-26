from pydantic import BaseModel, ConfigDict
from datetime import datetime
from src.schemas import MovieListItemSchema, GenreSchema


class MovieCartSchema(MovieListItemSchema):
    price: float
    # genres: list[GenreListResponseSchema]
    genres: list[GenreSchema]

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class CartItemSchema(BaseModel):
    id: int
    movie: MovieCartSchema
    added_at: datetime

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class CartSchema(BaseModel):
    id: int
    user_id: int
    items: list[CartItemSchema]

    model_config: ConfigDict = ConfigDict(from_attributes=True)
