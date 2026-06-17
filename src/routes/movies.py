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
    CertificationModel
)

from schemas import (
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieCreateSchema,
    MovieDetailSchema, CertificationSchema, GenreCreateSchema, DirectorSchema, DirectorCreateSchema, StarSchema,
    StarCreateSchema, GenreSchema
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
            "The response includes details about the movies, total pages, and total items, "
            "along with links to the previous and next pages if applicable.</h3>"
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
        db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Fetch a paginated list of movies from the database (asynchronously).

    This function retrieves a paginated list of movies, allowing the client to specify
    the page number and the number of items per page. It calculates the total pages
    and provides links to the previous and next pages when applicable.

    :param page: The page number to retrieve (1-based index, must be >= 1).
    :type page: int
    :param per_page: The number of items to display per page (must be between 1 and 20).
    :type per_page: int
    :param db: The async SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :return: A response containing the paginated list of movies and metadata.
    :rtype: MovieListResponseSchema

    :raises HTTPException: Raises a 404 error if no movies are found for the requested page.
    """
    offset = (page - 1) * per_page

    count_stmt = select(func.count(MovieModel.id))
    result_count = await db.execute(count_stmt)
    total_items = result_count.scalar() or 0

    if not total_items:
        raise HTTPException(status_code=404, detail="No movies found.")

    order_by = MovieModel.default_order_by()
    stmt = select(MovieModel).options(
        joinedload(MovieModel.genres),
        joinedload(MovieModel.certification),
    )
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
        prev_page=f"/api/v1/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None,
        next_page=f"/api/v1/movies/?page={page + 1}&per_page={per_page}" if page < total_pages else None,
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
