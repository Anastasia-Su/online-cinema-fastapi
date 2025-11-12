from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from src.schemas import MovieListItemSchema


class GenreCountSchema(BaseModel):
    id: int
    name: str
    movie_count: Optional[int] = None  # Included for genre listing with counts

    model_config: ConfigDict = ConfigDict(from_attributes=True) 
    
    
class GenreListResponseSchema(BaseModel):
    genres: list[GenreCountSchema]

    model_config: ConfigDict = ConfigDict(from_attributes=True)
    
# class GenreDetailSchema(GenreSchema):
#     movie_count: Optional[int] = None 
#     movies: list[MovieListItemSchema]
    