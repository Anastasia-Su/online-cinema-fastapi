from typing import Optional, Annotated
from datetime import date
from fastapi import HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from src.database import profile_validators


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

    @field_validator("year")
    @classmethod
    def validate_release_year(cls, v: int) -> int:
        current_year = datetime.now().year
        if v > current_year + 5:
            raise ValueError(f"Release year cannot be more than 5 years in the future")
        if v < 1895:
            raise ValueError("Movies didn't exist before 1895")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_field(cls, name: str) -> str:
        if name is None:
            raise ValueError("Name is required")
        try:

            profile_validators.validate_name(name)
            return name.lower()
        except ValueError as e:
            raise ValueError(str(e))

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Description is too short (minimum 10 characters)")
        if len(v) > 5000:
            raise ValueError("Description is too long (maximum 5000 characters)")
        return v.strip()

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        if v < 5:
            raise ValueError("Movie can't be shorter than 5 minutes")
        if v > 5 * 60:
            raise ValueError("Movie can't be longer than 5 hours")
        return v

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

    favorite_count: int
    like_count: int
    comment_count: int
    rating_average: float
    # user_has_favorited: bool = False
    # user_rating: Optional[int] = None
    # user_reaction: Optional[bool] = None

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieListItemSchema(BaseModel):
    id: int
    name: str
    year: int
    time: int
    imdb: float
    # favorite_count: int
    # like_count: int

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class MovieListResponseSchema(BaseModel):
    movies: list[MovieListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int

    model_config: ConfigDict = ConfigDict(from_attributes=True)
