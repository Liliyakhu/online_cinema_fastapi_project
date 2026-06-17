from sqlalchemy import or_
from typing import Optional, Literal

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
    CertificationModel, FavoritesModel
)

from schemas import (
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieCreateSchema,
    MovieDetailSchema, CertificationSchema, GenreCreateSchema, DirectorSchema, DirectorCreateSchema, StarSchema,
    StarCreateSchema, GenreSchema, MessageResponseSchema
)

from config.dependencies import get_current_user_id
from schemas.movies import CertificationCreateSchema

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
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MovieListResponseSchema:
    base_stmt = (
        select(MovieModel)
        .join(MovieModel.favorited_by)
        .where(UserModel.id == user_id)
        .distinct()
    )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    result_count = await db.execute(count_stmt)
    total_items = result_count.scalar() or 0

    if not total_items:
        raise HTTPException(status_code=404, detail="No favorite movies found.")

    offset = (page - 1) * per_page

    stmt = base_stmt.options(
        joinedload(MovieModel.genres),
        joinedload(MovieModel.certification),
    ).offset(offset).limit(per_page)

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

    return MovieDetailSchema.model_validate(movie)


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
