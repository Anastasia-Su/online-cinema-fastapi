from typing import Optional
from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class CertificationSchema(BaseModel):
    id: int
    name: str

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class GenreSchema(BaseModel):
    id: int
    name: str

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class StarSchema(BaseModel):
    id: int
    name: str

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class DirectorSchema(BaseModel):
    id: int
    name: str

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieBaseSchema(BaseModel):
    name: str = Field(..., max_length=255)
    year: int
    time: int
    imdb: float
    votes: int
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: str
    price: float
    certification_id: int

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieCreateSchema(MovieBaseSchema):
    genres: list[str]
    stars: list[str]
    directors: list[str]

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieUpdateSchema(BaseModel):
    name: Optional[str] = None
    year: Optional[int] = None
    time: Optional[int] = None
    imdb: Optional[float] = None
    votes: Optional[int] = None
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: Optional[str] = None
    price: Optional[float] = None
    certification_id: Optional[int] = None
    genres: Optional[list[str]] = None
    stars: Optional[list[str]] = None
    directors: Optional[list[str]] = None

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieDetailSchema(MovieBaseSchema):
    id: int
    certification: CertificationSchema
    genres: list[GenreSchema]
    stars: list[StarSchema]
    directors: list[DirectorSchema]

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieListItemSchema(BaseModel):
    id: int
    name: str
    year: int
    time: int
    imdb: float

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieListResponseSchema(BaseModel):
    movies: list[MovieListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int

    model_config: ConfigDict = ConfigDict(from_attributes=True)
