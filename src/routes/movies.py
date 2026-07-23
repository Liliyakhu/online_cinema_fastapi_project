from typing import Optional, Literal, List

from fastapi import APIRouter, Depends, Query, status

from config.dependencies import get_current_user_id, get_optional_user_id, get_movie_service
from schemas import (
    MovieListResponseSchema, MovieDetailSchema, MovieCreateSchema, MovieUpdateSchema,
    MovieLikeRequestSchema, MovieLikeResponseSchema, MovieRatingRequestSchema,
    MovieRatingResponseSchema, CommentCreateSchema, CommentResponseSchema,
    GenreWithCountSchema, GenreSchema, GenreCreateSchema, StarSchema, StarCreateSchema,
    DirectorSchema, DirectorCreateSchema, CertificationSchema, CertificationCreateSchema,
    MessageResponseSchema,
)
from services.movies import MovieService

router = APIRouter()


@router.get(
    "/movies/",
    response_model=MovieListResponseSchema,
    summary="Get a paginated list of movies",
    responses={
        404: {
            "description": "No movies found.",
            "content": {"application/json": {"example": {"detail": "No movies found."}}},
        }
    }
)
async def get_movie_list(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    search: Optional[str] = Query(None),
    genre_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    sort_by: Optional[Literal["price", "year", "imdb", "votes"]] = Query(None),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    service: MovieService = Depends(get_movie_service),
) -> MovieListResponseSchema:
    return await service.get_movie_list(page, per_page, search, genre_id, year, sort_by, sort_order)


@router.get(
    "/movies/favorites/",
    response_model=MovieListResponseSchema,
    summary="Get a paginated list of favorite movies",
    responses={
        404: {
            "description": "No favorite movies found.",
            "content": {"application/json": {"example": {"detail": "No favorite movies found."}}},
        }
    }
)
async def get_favorites(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    search: Optional[str] = Query(None),
    genre_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    sort_by: Optional[Literal["price", "year", "imdb", "votes"]] = Query(None),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MovieListResponseSchema:
    return await service.get_favorites(user_id, page, per_page, search, genre_id, year, sort_by, sort_order)


@router.get(
    "/movies/{movie_id}/",
    response_model=MovieDetailSchema,
    summary="Get movie details",
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie with the given ID was not found."}}},
        }
    }
)
async def get_movie(
    movie_id: int,
    user_id: Optional[int] = Depends(get_optional_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MovieDetailSchema:
    return await service.get_movie(movie_id, user_id)


@router.post(
    "/movies/",
    response_model=MovieDetailSchema,
    summary="Create a new movie",
    status_code=201,
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Related entity not found.",
            "content": {"application/json": {"example": {"detail": "Certification not found."}}},
        },
    }
)
async def create_movie(
    movie_data: MovieCreateSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MovieDetailSchema:
    return await service.create_movie(movie_data, user_id)


@router.patch(
    "/movies/{movie_id}/",
    response_model=MovieDetailSchema,
    summary="Update a movie by ID",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie with the given ID was not found."}}},
        },
    }
)
async def update_movie(
    movie_id: int,
    movie_data: MovieUpdateSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MovieDetailSchema:
    return await service.update_movie(movie_id, movie_data, user_id)


@router.delete(
    "/movies/{movie_id}/",
    summary="Delete a movie by ID",
    status_code=204,
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie with the given ID was not found."}}},
        },
        409: {
            "description": "Movie is in user carts.",
            "content": {"application/json": {"example": {
                "detail": "Cannot delete movie: it exists in 1 user cart(s)."
            }}},
        },
    }
)
async def delete_movie(
    movie_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
):
    await service.delete_movie(movie_id, user_id)


@router.post(
    "/movies/{movie_id}/favorites/",
    response_model=MessageResponseSchema,
    summary="Add movie to favorites",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
        409: {
            "description": "Movie already in favorites.",
            "content": {"application/json": {"example": {"detail": "Movie already in favorites."}}},
        },
    }
)
async def add_to_favorites(
    movie_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MessageResponseSchema:
    return await service.add_to_favorites(movie_id, user_id)


@router.delete(
    "/movies/{movie_id}/favorites/",
    response_model=MessageResponseSchema,
    summary="Remove movie from favorites",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
    }
)
async def delete_from_favorites(
    movie_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MessageResponseSchema:
    return await service.remove_from_favorites(movie_id, user_id)


@router.post(
    "/movies/{movie_id}/like/",
    response_model=MovieLikeResponseSchema,
    summary="Like/dislike a movie",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
    }
)
async def like_movie(
    movie_id: int,
    data: MovieLikeRequestSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MovieLikeResponseSchema:
    return await service.like_movie(movie_id, data, user_id)


@router.post(
    "/movies/{movie_id}/rate/",
    response_model=MovieRatingResponseSchema,
    summary="Rate a movie",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
    }
)
async def rate_movie(
    movie_id: int,
    data: MovieRatingRequestSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MovieRatingResponseSchema:
    return await service.rate_movie(movie_id, data, user_id)


@router.post(
    "/movies/{movie_id}/comments/",
    response_model=CommentResponseSchema,
    summary="Add a comment or reply to a movie",
    status_code=201,
    responses={
        404: {
            "description": "Movie or parent comment not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
    }
)
async def create_comment(
    movie_id: int,
    data: CommentCreateSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> CommentResponseSchema:
    return await service.create_comment(movie_id, data, user_id)


@router.get(
    "/movies/{movie_id}/comments/",
    response_model=List[CommentResponseSchema],
    summary="Get all comments for a movie",
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
    }
)
async def get_comments(
    movie_id: int,
    service: MovieService = Depends(get_movie_service),
) -> List[CommentResponseSchema]:
    return await service.get_comments(movie_id)


@router.post(
    "/comments/{comment_id}/like/",
    response_model=MessageResponseSchema,
    summary="Like or unlike a comment",
    status_code=200,
    responses={
        404: {
            "description": "Comment not found.",
            "content": {"application/json": {"example": {"detail": "Comment not found."}}},
        },
    }
)
async def like_comment(
    comment_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> MessageResponseSchema:
    return await service.like_comment(comment_id, user_id)


@router.get(
    "/genres/",
    response_model=List[GenreWithCountSchema],
    summary="Get list of genres with movie count",
)
async def get_genres(
    service: MovieService = Depends(get_movie_service),
) -> List[GenreWithCountSchema]:
    return await service.get_genres()


@router.post(
    "/genres/",
    response_model=GenreSchema,
    summary="Create a new genre",
    status_code=201,
    responses={
        409: {
            "description": "Genre already exists.",
            "content": {"application/json": {"example": {"detail": "Genre already exists."}}},
        },
    }
)
async def create_genre(
    data: GenreCreateSchema,
    service: MovieService = Depends(get_movie_service),
) -> GenreSchema:
    return await service.create_genre(data)


@router.patch(
    "/genres/{genre_id}/",
    response_model=GenreSchema,
    summary="Update a genre by ID",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Genre not found.",
            "content": {"application/json": {"example": {"detail": "Genre not found."}}},
        },
        409: {
            "description": "Genre with this name already exists.",
            "content": {"application/json": {"example": {"detail": "Genre with this name already exists."}}},
        },
    }
)
async def update_genre(
    genre_id: int,
    data: GenreCreateSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> GenreSchema:
    return await service.update_genre(genre_id, data, user_id)


@router.delete(
    "/genres/{genre_id}/",
    summary="Delete a genre by ID",
    status_code=204,
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Genre not found.",
            "content": {"application/json": {"example": {"detail": "Genre not found."}}},
        },
        409: {
            "description": "Genre is used by movies.",
            "content": {"application/json": {"example": {
                "detail": "Cannot delete genre that is used by at least one movie."
            }}},
        },
    }
)
async def delete_genre(
    genre_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
):
    await service.delete_genre(genre_id, user_id)


@router.post(
    "/stars/",
    response_model=StarSchema,
    summary="Create a new star",
    status_code=201,
    responses={
        409: {
            "description": "Star already exists.",
            "content": {"application/json": {"example": {"detail": "Star already exists."}}},
        },
    }
)
async def create_star(
    data: StarCreateSchema,
    service: MovieService = Depends(get_movie_service),
) -> StarSchema:
    return await service.create_star(data)


@router.patch(
    "/stars/{star_id}/",
    response_model=StarSchema,
    summary="Update a star by ID",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Star not found.",
            "content": {"application/json": {"example": {"detail": "Star not found."}}},
        },
        409: {
            "description": "Star with this name already exists.",
            "content": {"application/json": {"example": {"detail": "Star with this name already exists."}}},
        },
    }
)
async def update_star(
    star_id: int,
    data: StarCreateSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> StarSchema:
    return await service.update_star(star_id, data, user_id)


@router.delete(
    "/stars/{star_id}/",
    summary="Delete a star by ID",
    status_code=204,
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Star not found.",
            "content": {"application/json": {"example": {"detail": "Star not found."}}},
        },
        409: {
            "description": "Star is used by movies.",
            "content": {"application/json": {"example": {
                "detail": "Cannot delete star that is used by at least one movie."
            }}},
        },
    }
)
async def delete_star(
    star_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
):
    await service.delete_star(star_id, user_id)


@router.post(
    "/directors/",
    response_model=DirectorSchema,
    summary="Create a new director",
    status_code=201,
    responses={
        409: {
            "description": "Director already exists.",
            "content": {"application/json": {"example": {"detail": "Director already exists."}}},
        },
    }
)
async def create_director(
    data: DirectorCreateSchema,
    service: MovieService = Depends(get_movie_service),
) -> DirectorSchema:
    return await service.create_director(data)


@router.patch(
    "/directors/{director_id}/",
    response_model=DirectorSchema,
    summary="Update a director by ID",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Director not found.",
            "content": {"application/json": {"example": {"detail": "Director not found."}}},
        },
        409: {
            "description": "Director with this name already exists.",
            "content": {"application/json": {"example": {"detail": "Director with this name already exists."}}},
        },
    }
)
async def update_director(
    director_id: int,
    data: DirectorCreateSchema,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
) -> DirectorSchema:
    return await service.update_director(director_id, data, user_id)


@router.delete(
    "/directors/{director_id}/",
    summary="Delete a director by ID",
    status_code=204,
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Director not found.",
            "content": {"application/json": {"example": {"detail": "Director not found."}}},
        },
        409: {
            "description": "Director is used by movies.",
            "content": {"application/json": {"example": {
                "detail": "Cannot delete director that is used by at least one movie."
            }}},
        },
    }
)
async def delete_director(
    director_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MovieService = Depends(get_movie_service),
):
    await service.delete_director(director_id, user_id)


@router.post(
    "/certifications/",
    response_model=CertificationSchema,
    summary="Create a new certification",
    status_code=201,
    responses={
        409: {
            "description": "Certification already exists.",
            "content": {"application/json": {"example": {"detail": "Certification already exists."}}},
        },
    }
)
async def create_certification(
    data: CertificationCreateSchema,
    service: MovieService = Depends(get_movie_service),
) -> CertificationSchema:
    return await service.create_certification(data)
