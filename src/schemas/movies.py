from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


class GenreSchema(BaseModel):
    id: int
    name: str

    model_config = {
        "from_attributes": True,
    }


class StarSchema(BaseModel):
    id: int
    name: str

    model_config = {
        "from_attributes": True,
    }


class DirectorSchema(BaseModel):
    id: int
    name: str

    model_config = {
        "from_attributes": True,
    }


class CertificationSchema(BaseModel):
    id: int
    name: str

    model_config = {
        "from_attributes": True,
    }


class MovieBaseSchema(BaseModel):
    name: str = Field(..., max_length=255)
    year: int
    imdb: float
    price: float

    @field_validator("year")
    @classmethod
    def validate_year(cls, value):
        current_year = datetime.now().year
        if value > current_year + 1:
            raise ValueError(f"Year cannot be greater than {current_year + 1}.")
        return value


class MovieDetailSchema(MovieBaseSchema):
    id: int
    time: int
    votes: int
    meta_score: Optional[float]
    gross: Optional[float]
    description: str
    certification: CertificationSchema
    genres: List[GenreSchema]
    stars: List[StarSchema]
    directors: List[DirectorSchema]
    likes_count: int = 0
    dislikes_count: int = 0
    average_rating: Optional[float] = None
    total_ratings: int = 0
    user_like: Optional[bool] = None
    user_rating: Optional[int] = None

    model_config = {"from_attributes": True}


class MovieListItemSchema(MovieBaseSchema):
    id: int
    genres: List[GenreSchema]
    certification: CertificationSchema

    model_config = {"from_attributes": True}


class MovieListResponseSchema(BaseModel):
    items: List[MovieListItemSchema]
    total: int
    page: int
    per_page: int
    total_pages: int
    prev_page: Optional[str] = None
    next_page: Optional[str] = None


class MovieCreateSchema(MovieBaseSchema):
    time: int
    votes: int
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: str
    certification_id: int
    genre_ids: List[int]
    star_ids: List[int]
    director_ids: List[int]


class MovieUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    year: Optional[int] = None
    imdb: Optional[float] = None
    price: Optional[float] = None
    time: Optional[int] = None
    votes: Optional[int] = None
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: Optional[str] = None
    certification_id: Optional[int] = None
    genre_ids: Optional[List[int]] = None
    star_ids: Optional[List[int]] = None
    director_ids: Optional[List[int]] = None


class GenreCreateSchema(BaseModel):
    name: str = Field(..., max_length=255)


class StarCreateSchema(BaseModel):
    name: str = Field(..., max_length=255)


class DirectorCreateSchema(BaseModel):
    name: str = Field(..., max_length=255)


class CertificationCreateSchema(BaseModel):
    name: str = Field(..., max_length=255)


class MovieLikeRequestSchema(BaseModel):
    is_like: bool


class MovieLikeResponseSchema(BaseModel):
    likes_count: int
    dislikes_count: int
    user_like: Optional[bool] = None


class MovieRatingRequestSchema(BaseModel):
    rating: int = Field(..., ge=1, le=10)


class MovieRatingResponseSchema(BaseModel):
    average_rating: float
    total_ratings: int
    user_rating: Optional[int]
