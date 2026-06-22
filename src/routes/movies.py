from sqlalchemy.exc import IntegrityError

from sqlalchemy import or_
from typing import Optional, Literal, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload


from database import get_db, UserModel, UserGroupEnum
from database.models import (
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
    FavoritesModel,
    MovieLikeModel,
    MovieRatingModel,
    MovieCommentModel,
    MoviesGenresModel,
    CommentLikeModel,
    NotificationModel,
    MoviesDirectorsModel,
    StarsMoviesModel
)

from schemas import (
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieCreateSchema,
    MovieDetailSchema,
    CertificationSchema,
    CertificationCreateSchema,
    GenreCreateSchema,
    DirectorSchema,
    DirectorCreateSchema,
    StarSchema,
    StarCreateSchema,
    GenreSchema,
    MessageResponseSchema,
    MovieLikeResponseSchema,
    MovieLikeRequestSchema,
    MovieRatingRequestSchema,
    MovieRatingResponseSchema,
    CommentCreateSchema,
    CommentResponseSchema,
    GenreWithCountSchema,
    MovieUpdateSchema
)

from config.dependencies import get_current_user_id, get_optional_user_id

router = APIRouter()


@router.get(
    "/movies/",
    response_model=MovieListResponseSchema,
    summary="Get a paginated list of movies",
    description=(
            "<h3>This endpoint retrieves a paginated list of movies from the database. "
            "Clients can specify the `page` number and the number of items per page using `per_page`. "
            "Supports search, filtering by genre and year, and sorting.</h3>"
    ),
    responses={
        404: {
            "description": "No movies found.",
            "content": {
                "application/json": {
                    "example": {"detail": "No movies found."}
                }
            },
        }
    }
)
async def get_movie_list(
        page: int = Query(1, ge=1, description="Page number (1-based index)"),
        per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
        search: Optional[str] = Query(None, description="Search by title, description, actor, or director"),
        genre_id: Optional[int] = Query(None, description="Filter by genre ID"),
        year: Optional[int] = Query(None, description="Filter by release year"),
        sort_by: Optional[Literal["price", "year", "imdb", "votes"]] = Query(None, description="Sort field"),
        sort_order: Literal["asc", "desc"] = Query("desc", description="Sort order: asc or desc"),
        db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Fetch a paginated list of movies from the database (asynchronously).

    Supports searching by title/description/actor/director, filtering by genre
    and year, and sorting by price, year, imdb, or votes.
    """
    base_stmt = select(MovieModel)

    if search:
        base_stmt = (
            base_stmt
            .outerjoin(MovieModel.stars)
            .outerjoin(MovieModel.directors)
            .where(
                or_(
                    MovieModel.name.ilike(f"%{search}%"),
                    MovieModel.description.ilike(f"%{search}%"),
                    StarModel.name.ilike(f"%{search}%"),
                    DirectorModel.name.ilike(f"%{search}%"),
                )
            )
        )

    if genre_id:
        base_stmt = base_stmt.join(MovieModel.genres).where(GenreModel.id == genre_id)

    if year:
        base_stmt = base_stmt.where(MovieModel.year == year)

    base_stmt = base_stmt.distinct()

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    result_count = await db.execute(count_stmt)
    total_items = result_count.scalar() or 0

    if not total_items:
        raise HTTPException(status_code=404, detail="No movies found.")

    offset = (page - 1) * per_page

    stmt = base_stmt.options(
        joinedload(MovieModel.genres),
        joinedload(MovieModel.certification),
    )

    sortable_fields = {
        "price": MovieModel.price,
        "year": MovieModel.year,
        "imdb": MovieModel.imdb,
        "votes": MovieModel.votes,
    }

    if sort_by:
        column = sortable_fields[sort_by]
        stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())
    else:
        order_by = MovieModel.default_order_by()
        if order_by:
            stmt = stmt.order_by(*order_by)

    stmt = stmt.offset(offset).limit(per_page)

    result_movies = await db.execute(stmt)
    movies = result_movies.scalars().unique().all()

    if not movies:
        raise HTTPException(status_code=404, detail="No movies found.")

    movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]
    total_pages = (total_items + per_page - 1) // per_page

    response = MovieListResponseSchema(
        items=movie_list,
        total=total_items,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        prev_page=f"/api/v1/cinema/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None,
        next_page=f"/api/v1/cinema/movies/?page={page + 1}&per_page={per_page}" if page < total_pages else None,
    )
    return response


@router.post(
    "/movies/",
    response_model=MovieDetailSchema,
    summary="Create a new movie",
    description=(
            "<h3>This endpoint allows clients to add a new movie to the database. "
            "It accepts details such as name, year, genres, stars, directors, and "
            "other attributes. The associated certification, genres, stars, and directors "
            "will be created or linked automatically.</h3>"
    ),
    responses={
        201: {
            "description": "Movie created successfully.",
        },
        400: {
            "description": "Invalid input.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid input data."}
                }
            },
        }
    },
    status_code=201
)
async def create_movie(
        movie_data: MovieCreateSchema,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MovieDetailSchema:
    # Перевірка прав
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    # Перевірка certification
    cert = await db.get(CertificationModel, movie_data.certification_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found.")

    # Перевірка genres
    genres_result = await db.execute(
        select(GenreModel).where(GenreModel.id.in_(movie_data.genre_ids))
    )
    genres = genres_result.scalars().all()
    if len(genres) != len(movie_data.genre_ids):
        raise HTTPException(status_code=404, detail="One or more genres not found.")

    # Перевірка stars
    stars_result = await db.execute(
        select(StarModel).where(StarModel.id.in_(movie_data.star_ids))
    )
    stars = stars_result.scalars().all()
    if len(stars) != len(movie_data.star_ids):
        raise HTTPException(status_code=404, detail="One or more stars not found.")

    # Перевірка directors
    directors_result = await db.execute(
        select(DirectorModel).where(DirectorModel.id.in_(movie_data.director_ids))
    )
    directors = directors_result.scalars().all()
    if len(directors) != len(movie_data.director_ids):
        raise HTTPException(status_code=404, detail="One or more directors not found.")

    # Створення фільму
    movie = MovieModel(
        name=movie_data.name,
        year=movie_data.year,
        time=movie_data.time,
        imdb=movie_data.imdb,
        votes=movie_data.votes,
        meta_score=movie_data.meta_score,
        gross=movie_data.gross,
        description=movie_data.description,
        price=movie_data.price,
        certification_id=movie_data.certification_id,
        genres=genres,
        stars=stars,
        directors=directors,
    )
    db.add(movie)
    await db.commit()
    await db.refresh(movie)

    result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.certification),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.stars),
            joinedload(MovieModel.directors),
        )
        .filter_by(id=movie.id)
    )
    movie = result.scalars().unique().first()

    return MovieDetailSchema.model_validate(movie)


@router.post(
    "/genres/",
    response_model=GenreSchema,
    summary="Create a new genre",
    status_code=201,
)
async def create_genre(
        data: GenreCreateSchema,
        db: AsyncSession = Depends(get_db),
) -> GenreSchema:
    existing = await db.execute(select(GenreModel).where(GenreModel.name == data.name))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Genre already exists.")

    genre = GenreModel(name=data.name)
    db.add(genre)
    await db.commit()
    await db.refresh(genre)
    return GenreSchema.model_validate(genre)


@router.post(
    "/stars/",
    response_model=StarSchema,
    summary="Create a new star",
    status_code=201,
)
async def create_star(
        data: StarCreateSchema,
        db: AsyncSession = Depends(get_db),
) -> StarSchema:
    existing = await db.execute(select(StarModel).where(StarModel.name == data.name))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Star already exists.")

    star = StarModel(name=data.name)
    db.add(star)
    await db.commit()
    await db.refresh(star)
    return StarSchema.model_validate(star)


@router.post(
    "/directors/",
    response_model=DirectorSchema,
    summary="Create a new director",
    status_code=201,
)
async def create_director(
        data: DirectorCreateSchema,
        db: AsyncSession = Depends(get_db),
) -> DirectorSchema:
    existing = await db.execute(select(DirectorModel).where(DirectorModel.name == data.name))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Director already exists.")

    director = DirectorModel(name=data.name)
    db.add(director)
    await db.commit()
    await db.refresh(director)
    return DirectorSchema.model_validate(director)


@router.post(
    "/certifications/",
    response_model=CertificationSchema,
    summary="Create a new certification",
    status_code=201,
)
async def create_certification(
        data: CertificationCreateSchema,
        db: AsyncSession = Depends(get_db),
) -> CertificationSchema:
    existing = await db.execute(select(CertificationModel).where(CertificationModel.name == data.name))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Certification already exists.")

    certification = CertificationModel(name=data.name)
    db.add(certification)
    await db.commit()
    await db.refresh(certification)
    return CertificationSchema.model_validate(certification)


@router.get(
    "/movies/favorites/",
    response_model=MovieListResponseSchema,
    summary="Get a paginated list of favorite movies",
    responses={
        404: {
            "description": "No favorite movies found.",
            "content": {
                "application/json": {
                    "example": {"detail": "No favorite movies found."}
                }
            },
        }
    }
)
async def get_favorites(
        page: int = Query(1, ge=1, description="Page number (1-based index)"),
        per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
        search: Optional[str] = Query(None, description="Search by title, description, actor, or director"),
        genre_id: Optional[int] = Query(None, description="Filter by genre ID"),
        year: Optional[int] = Query(None, description="Filter by release year"),
        sort_by: Optional[Literal["price", "year", "imdb", "votes"]] = Query(None, description="Sort field"),
        sort_order: Literal["asc", "desc"] = Query("desc", description="Sort order: asc or desc"),
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MovieListResponseSchema:
    base_stmt = (
        select(MovieModel)
        .join(MovieModel.favorited_by)
        .where(UserModel.id == user_id)
        .distinct()
    )

    if search:
        base_stmt = (
            base_stmt
            .outerjoin(MovieModel.stars)
            .outerjoin(MovieModel.directors)
            .where(
                or_(
                    MovieModel.name.ilike(f"%{search}%"),
                    MovieModel.description.ilike(f"%{search}%"),
                    StarModel.name.ilike(f"%{search}%"),
                    DirectorModel.name.ilike(f"%{search}%"),
                )
            )
        )

    if genre_id:
        base_stmt = base_stmt.join(MovieModel.genres).where(GenreModel.id == genre_id)

    if year:
        base_stmt = base_stmt.where(MovieModel.year == year)

    base_stmt = base_stmt.distinct()
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    result_count = await db.execute(count_stmt)
    total_items = result_count.scalar() or 0

    if not total_items:
        raise HTTPException(status_code=404, detail="No favorite movies found.")

    offset = (page - 1) * per_page

    stmt = base_stmt.options(
        joinedload(MovieModel.genres),
        joinedload(MovieModel.certification),
    )

    sortable_fields = {
        "price": MovieModel.price,
        "year": MovieModel.year,
        "imdb": MovieModel.imdb,
        "votes": MovieModel.votes,
    }

    if sort_by:
        column = sortable_fields[sort_by]
        stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())
    else:
        order_by = MovieModel.default_order_by()
        if order_by:
            stmt = stmt.order_by(*order_by)

    stmt = stmt.offset(offset).limit(per_page)

    result_movies = await db.execute(stmt)
    movies = result_movies.scalars().unique().all()

    movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]
    total_pages = (total_items + per_page - 1) // per_page

    return MovieListResponseSchema(
        items=movie_list,
        total=total_items,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        prev_page=f"/api/v1/cinema/movies/favorites/?page={page - 1}&per_page={per_page}" if page > 1 else None,
        next_page=f"/api/v1/cinema/movies/favorites/?page={page + 1}&per_page={per_page}" if page < total_pages else None,
    )


@router.get(
    "/movies/{movie_id}/",
    response_model=MovieDetailSchema,
    summary="Get movie details",
    description="Retrieve detailed information about a specific movie by its ID.",
    responses={
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        }
    }
)
async def get_movie(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: Optional[int] = Depends(get_optional_user_id),
) -> MovieDetailSchema:
    result = await db.execute(
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            joinedload(MovieModel.certification),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.stars),
            joinedload(MovieModel.directors),
        )
    )
    movie = result.unique().scalar_one_or_none()

    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    likes_result = await db.execute(
        select(func.count()).select_from(MovieLikeModel).where(
            MovieLikeModel.movie_id == movie_id, MovieLikeModel.is_like == True
        )
    )
    likes_count = likes_result.scalar() or 0

    dislikes_result = await db.execute(
        select(func.count()).select_from(MovieLikeModel).where(
            MovieLikeModel.movie_id == movie_id, MovieLikeModel.is_like == False
        )
    )
    dislikes_count = dislikes_result.scalar() or 0

    avg_result = await db.execute(
        select(func.avg(MovieRatingModel.rating)).where(MovieRatingModel.movie_id == movie_id)
    )
    average_rating = avg_result.scalar()

    total_ratings_result = await db.execute(
        select(func.count()).select_from(MovieRatingModel).where(MovieRatingModel.movie_id == movie_id)
    )
    total_ratings = total_ratings_result.scalar() or 0

    user_like = None
    user_rating = None
    if user_id:
        user_like_result = await db.execute(
            select(MovieLikeModel.is_like).where(
                MovieLikeModel.movie_id == movie_id,
                MovieLikeModel.user_id == user_id,
            )
        )
        user_like = user_like_result.scalar_one_or_none()

        user_rating_result = await db.execute(
            select(MovieRatingModel.rating).where(
                MovieRatingModel.movie_id == movie_id,
                MovieRatingModel.user_id == user_id,
            )
        )
        user_rating = user_rating_result.scalar_one_or_none()

    movie_data = MovieDetailSchema.model_validate(movie)
    movie_data.likes_count = likes_count
    movie_data.dislikes_count = dislikes_count
    movie_data.average_rating = round(average_rating, 1) if average_rating else None
    movie_data.total_ratings = total_ratings
    movie_data.user_like = user_like
    movie_data.user_rating = user_rating

    return movie_data


@router.post(
    "/movies/{movie_id}/favorites/",
    response_model=MessageResponseSchema,
    summary="Add movie to favorites",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        },
        409: {
            "description": "Movie already in favorites.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie already in favorites."}
                }
            },
        },
    }
)
async def add_to_favorites(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.favorite_movies))
        .filter_by(id=user_id)
    )
    current_user = result.unique().scalars().first()

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    if movie in current_user.favorite_movies:
        raise HTTPException(status_code=409, detail="Movie already in favorites.")

    current_user.favorite_movies.append(movie)
    await db.commit()

    return MessageResponseSchema(message="Movie added to favorites.")


@router.delete(
    "/movies/{movie_id}/favorites/",
    response_model=MessageResponseSchema,
    summary="Remove movie from favorites",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        },
    }
)
async def delete_from_favorites(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.favorite_movies))
        .filter_by(id=user_id)
    )
    current_user = result.unique().scalars().first()

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    if movie not in current_user.favorite_movies:
        raise HTTPException(status_code=409, detail="Movie is not in favorites.")

    current_user.favorite_movies.remove(movie)
    await db.commit()

    return MessageResponseSchema(message="Movie deleted from favorites.")


@router.post(
    "/movies/{movie_id}/like/",
    response_model=MovieLikeResponseSchema,
    summary="Like/dislike a movie",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        },
    }
)
async def like_movie(
        data: MovieLikeRequestSchema,
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MovieLikeResponseSchema:

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    existing_like = await db.execute(
        select(MovieLikeModel).where(
            MovieLikeModel.movie_id == movie_id,
            MovieLikeModel.user_id == user_id,
        )
    )
    existing_like = existing_like.scalars().first()

    if not existing_like:
        new_like = MovieLikeModel(user_id=user_id, movie_id=movie_id, is_like=data.is_like)
        db.add(new_like)
    elif existing_like.is_like == data.is_like:
        await db.delete(existing_like)
    else:
        existing_like.is_like = data.is_like

    await db.commit()

    likes_result = await db.execute(
        select(func.count()).select_from(MovieLikeModel).where(
            MovieLikeModel.movie_id == movie_id,
            MovieLikeModel.is_like == True
        )
    )
    likes_count = likes_result.scalar() or 0

    dislikes_result = await db.execute(
        select(func.count()).select_from(MovieLikeModel).where(
            MovieLikeModel.movie_id == movie_id,
            MovieLikeModel.is_like == False
        )
    )
    dislikes_count = dislikes_result.scalar() or 0

    current_reaction_result = await db.execute(
        select(MovieLikeModel.is_like).where(
            MovieLikeModel.movie_id == movie_id,
            MovieLikeModel.user_id == user_id,
        )
    )
    user_like = current_reaction_result.scalar_one_or_none()

    return MovieLikeResponseSchema(
        likes_count=likes_count,
        dislikes_count=dislikes_count,
        user_like=user_like,
    )


@router.post(
    "/movies/{movie_id}/rate/",
    response_model=MovieRatingResponseSchema,
    summary="Rate a movie",
    status_code=200,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        },
    }
)
async def rate_movie(
        data: MovieRatingRequestSchema,
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MovieRatingResponseSchema:

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    existing_rating = await db.execute(
        select(MovieRatingModel).where(
            MovieRatingModel.movie_id == movie_id,
            MovieRatingModel.user_id == user_id,
        )
    )
    existing_rating = existing_rating.scalars().first()

    if not existing_rating:
        new_rating = MovieRatingModel(user_id=user_id, movie_id=movie_id, rating=data.rating)
        db.add(new_rating)
    else:
        existing_rating.rating = data.rating

    await db.commit()

    avg_result = await db.execute(
        select(func.avg(MovieRatingModel.rating)).where(MovieRatingModel.movie_id == movie_id)
    )
    avg_result = avg_result.scalar() or 0

    total_ratings = await db.execute(
        select(func.count()).select_from(MovieRatingModel).where(
            MovieRatingModel.movie_id == movie_id,
        )
    )
    total_ratings = total_ratings.scalar() or 0

    user_rating = await db.execute(
        select(MovieRatingModel.rating).where(
            MovieRatingModel.movie_id == movie_id,
            MovieRatingModel.user_id == user_id,
        )
    )
    user_rating = user_rating.scalar_one_or_none()

    return MovieRatingResponseSchema(
        average_rating=avg_result,
        total_ratings=total_ratings,
        user_rating=user_rating
    )


@router.post(
    "/movies/{movie_id}/comments/",
    response_model=CommentResponseSchema,
    summary="Add a comment or reply to a movie",
    status_code=201,
    responses={
        404: {
            "description": "Movie or parent comment not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        },
    }
)
async def create_comment(
        movie_id: int,
        data: CommentCreateSchema,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> CommentResponseSchema:
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    parent_id = data.parent_id if data.parent_id and data.parent_id > 0 else None

    if parent_id:
        parent_comment = await db.get(MovieCommentModel, parent_id)
        if not parent_comment or parent_comment.movie_id != movie_id:
            raise HTTPException(status_code=404, detail="Parent comment not found.")
        if parent_comment.parent_id:
            raise HTTPException(status_code=400, detail="Cannot reply to a reply.")

        if parent_comment.user_id != user_id:
            notification = NotificationModel(
                user_id=parent_comment.user_id,
                message="Your comment received a new reply.",
            )
            db.add(notification)

    comment = MovieCommentModel(
        user_id=user_id,
        movie_id=movie_id,
        parent_id=parent_id,
        text=data.text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    result = await db.execute(
        select(MovieCommentModel)
        .where(MovieCommentModel.id == comment.id)
        .options(joinedload(MovieCommentModel.replies))
    )
    comment = result.unique().scalar_one()

    return CommentResponseSchema.model_validate(comment)


@router.get(
    "/movies/{movie_id}/comments/",
    response_model=List[CommentResponseSchema],
    summary="Get all comments for a movie",
    responses={
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie not found."}
                }
            },
        },
    }
)
async def get_comments(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
) -> List[CommentResponseSchema]:
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    result = await db.execute(
        select(MovieCommentModel)
        .where(
            MovieCommentModel.movie_id == movie_id,
            MovieCommentModel.parent_id.is_(None),
        )
        .options(joinedload(MovieCommentModel.replies).joinedload(MovieCommentModel.replies))
        .order_by(MovieCommentModel.created_at.desc())
    )
    comments = result.unique().scalars().all()

    return [CommentResponseSchema.model_validate(comment) for comment in comments]


@router.get(
    "/genres/",
    response_model=List[GenreWithCountSchema],
    summary="Get list of genres with movie count",
)
async def get_genres(
        db: AsyncSession = Depends(get_db),
) -> List[GenreWithCountSchema]:
    stmt = (
        select(GenreModel.id, GenreModel.name, func.count(MoviesGenresModel.c.movie_id).label("movies_count"))
        .outerjoin(MoviesGenresModel, GenreModel.id == MoviesGenresModel.c.genre_id)
        .group_by(GenreModel.id)
        .order_by(GenreModel.name)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        GenreWithCountSchema(id=row.id, name=row.name, movies_count=row.movies_count)
        for row in rows
    ]


@router.post(
    "/comments/{comment_id}/like/",
    response_model=MessageResponseSchema,
    summary="Like or unlike a comment",
    status_code=200,
    responses={
        404: {
            "description": "Comment not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Comment not found."}
                }
            },
        },
    }
)
async def like_comment(
        comment_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    comment = await db.get(MovieCommentModel, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found.")

    existing_like = await db.execute(
        select(CommentLikeModel).where(
            CommentLikeModel.comment_id == comment_id,
            CommentLikeModel.user_id == user_id,
        )
    )
    existing_like = existing_like.scalars().first()

    if existing_like:
        await db.delete(existing_like)
        await db.commit()
        return MessageResponseSchema(message="Comment unliked.")

    new_like = CommentLikeModel(user_id=user_id, comment_id=comment_id)
    db.add(new_like)

    if comment.user_id != user_id:
        notification = NotificationModel(
            user_id=comment.user_id,
            message="Your comment received a new like.",
        )
        db.add(notification)

    await db.commit()

    return MessageResponseSchema(message="Comment liked.")


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
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MovieDetailSchema:
    # Перевірка прав
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    movie_result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.genres),
            joinedload(MovieModel.stars),
            joinedload(MovieModel.directors),
        )
        .filter_by(id=movie_id)
    )
    movie = movie_result.unique().scalar_one_or_none()

    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    update_data = movie_data.model_dump(exclude_unset=True)

    if "genre_ids" in update_data:
        genre_ids = update_data.pop("genre_ids")
        genres_result = await db.execute(select(GenreModel).where(GenreModel.id.in_(genre_ids)))
        movie.genres = genres_result.scalars().all()

    if "star_ids" in update_data:
        star_ids = update_data.pop("star_ids")
        stars_result = await db.execute(select(StarModel).where(StarModel.id.in_(star_ids)))
        movie.stars = stars_result.scalars().all()

    if "director_ids" in update_data:
        director_ids = update_data.pop("director_ids")
        directors_result = await db.execute(select(DirectorModel).where(DirectorModel.id.in_(director_ids)))
        movie.directors = directors_result.scalars().all()

    if "certification_id" in update_data:
        cert = await db.get(CertificationModel, update_data["certification_id"])
        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found.")

    for field, value in update_data.items():
        setattr(movie, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")

    result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.certification),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.stars),
            joinedload(MovieModel.directors),
        )
        .filter_by(id=movie.id)
    )
    movie = result.scalars().unique().first()

    return MovieDetailSchema.model_validate(movie)


@router.delete(
    "/movies/{movie_id}/",
    summary="Delete a movie by ID",
    description=(
            "<h3>Delete a specific movie from the database by its unique ID.</h3>"
            "<p>If the movie exists, it will be deleted. If it does not exist, "
            "a 404 error will be returned.</p>"
    ),
    responses={
        204: {
            "description": "Movie deleted successfully."
        },
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        },
    },
    status_code=204
)
async def delete_movie(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
):
    # Перевірка прав
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=404,
            detail="Movie with the given ID was not found."
        )

    # TODO: Prevent deletion if at least one user has purchased the movie (requires future Order/Purchase model)

    await db.delete(movie)
    await db.commit()


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
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> GenreSchema:
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    genre = await db.get(GenreModel, genre_id)
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found.")

    existing = await db.execute(
        select(GenreModel).where(GenreModel.name == data.name, GenreModel.id != genre_id)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Genre with this name already exists.")

    genre.name = data.name

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")

    await db.refresh(genre)
    return GenreSchema.model_validate(genre)


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
    }
)
async def delete_genre(
        genre_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    genre = await db.get(GenreModel, genre_id)
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found.")

    movies_count_result = await db.execute(
        select(func.count()).select_from(MoviesGenresModel).where(MoviesGenresModel.c.genre_id == genre_id)
    )
    movies_count = movies_count_result.scalar() or 0
    if movies_count > 0:
        raise HTTPException(status_code=409, detail="Cannot delete genre that is used by at least one movie.")

    await db.delete(genre)
    await db.commit()


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
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> StarSchema:
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    star = await db.get(StarModel, star_id)
    if not star:
        raise HTTPException(status_code=404, detail="Star not found.")

    existing = await db.execute(
        select(StarModel).where(StarModel.name == data.name, StarModel.id != star_id)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Star with this name already exists.")

    star.name = data.name

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")

    await db.refresh(star)
    return StarSchema.model_validate(star)


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
    }
)
async def delete_star(
        star_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    star = await db.get(StarModel, star_id)
    if not star:
        raise HTTPException(status_code=404, detail="Star not found.")

    movies_count_result = await db.execute(
        select(func.count()).select_from(StarsMoviesModel).where(StarsMoviesModel.c.star_id == star_id)
    )
    movies_count = movies_count_result.scalar() or 0
    if movies_count > 0:
        raise HTTPException(status_code=409, detail="Cannot delete star that is used by at least one movie.")

    await db.delete(star)
    await db.commit()


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
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> DirectorSchema:
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    director = await db.get(DirectorModel, director_id)
    if not director:
        raise HTTPException(status_code=404, detail="Director not found.")

    existing = await db.execute(
        select(DirectorModel).where(DirectorModel.name == data.name, DirectorModel.id != director_id)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Director with this name already exists.")

    director.name = data.name

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")

    await db.refresh(director)
    return DirectorSchema.model_validate(director)


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
    }
)
async def delete_director(
        director_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    director = await db.get(DirectorModel, director_id)
    if not director:
        raise HTTPException(status_code=404, detail="Director not found.")

    movies_count_result = await db.execute(
        select(func.count()).select_from(MoviesDirectorsModel).where(MoviesDirectorsModel.c.director_id == director_id)
    )
    movies_count = movies_count_result.scalar() or 0
    if movies_count > 0:
        raise HTTPException(status_code=409, detail="Cannot delete director that is used by at least one movie.")

    await db.delete(director)
    await db.commit()


