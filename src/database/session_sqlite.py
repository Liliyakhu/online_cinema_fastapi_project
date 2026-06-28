from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from config.dependencies import get_settings
from database.models import MovieModel, DirectorModel, StarModel, GenreModel, CertificationModel
from database.models.base import Base
from database.models.accounts import UserGroupModel, UserGroupEnum, UserModel

settings = get_settings()

DATABASE_URL = f"sqlite+aiosqlite:///{settings.PATH_TO_DB}"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSQLiteSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore


async def init_db() -> None:
    """
    Initialize the database.

    This function creates all tables defined in the SQLAlchemy ORM models.
    It should be called at the application startup to ensure that the database schema exists.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close the database connection.

    This function disposes of the database engine, releasing all associated resources.
    It should be called when the application shuts down to properly close the connection pool.
    """
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an asynchronous database session.

    This function returns an async generator yielding a new database session.
    It ensures that the session is properly closed after use.

    :return: An asynchronous generator yielding an AsyncSession instance.
    """
    async with AsyncSQLiteSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_db_contextmanager() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an asynchronous database session using a context manager.

    This function allows for managing the database session within a `with` statement.
    It ensures that the session is properly initialized and closed after execution.

    :return: An asynchronous generator yielding an AsyncSession instance.
    """
    async with AsyncSQLiteSessionLocal() as session:
        yield session


async def reset_sqlite_database() -> None:
    """
    Reset the SQLite database.

    This function drops all existing tables and recreates them.
    It is useful for testing purposes or when resetting the database is required.

    Warning: This action is irreversible and will delete all stored data.

    :return: None
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def create_default_groups() -> None:
    async with AsyncSQLiteSessionLocal() as session:
        for group_name in UserGroupEnum:
            stmt = select(UserGroupModel).where(UserGroupModel.name == group_name)
            result = await session.execute(stmt)
            if not result.scalars().first():
                session.add(UserGroupModel(name=group_name))
        await session.commit()


async def create_test_users() -> None:
    async with AsyncSQLiteSessionLocal() as session:
        for email, password, group_name in [
            ("admin@admin.com", "Admin123&", UserGroupEnum.ADMIN),
            ("user@user.com", "User123$", UserGroupEnum.USER),
        ]:
            stmt = select(UserModel).where(UserModel.email == email)
            result = await session.execute(stmt)
            if not result.scalars().first():
                stmt = select(UserGroupModel).where(UserGroupModel.name == group_name)
                result = await session.execute(stmt)
                user_group = result.scalars().first()
                user = UserModel.create(
                    email=email,
                    raw_password=password,
                    group_id=user_group.id
                )
                user.is_active = True
                session.add(user)
        await session.commit()


async def create_test_movies() -> None:
    async with AsyncSQLiteSessionLocal() as session:
        stmt = select(MovieModel).where(MovieModel.name == "Inception")
        result = await session.execute(stmt)
        if result.scalars().first():
            return  # фільми вже є

        certification = CertificationModel(name="PG-13")
        session.add(certification)
        await session.flush()

        genre_action = GenreModel(name="Action")
        genre_scifi = GenreModel(name="Sci-Fi")
        genre_crime = GenreModel(name="Crime")
        genre_drama = GenreModel(name="Drama")
        session.add_all([genre_action, genre_scifi, genre_crime, genre_drama])
        await session.flush()

        star_dicaprio = StarModel(name="Leonardo DiCaprio")
        star_bale = StarModel(name="Christian Bale")
        star_ledger = StarModel(name="Heath Ledger")
        session.add_all([star_dicaprio, star_bale, star_ledger])
        await session.flush()

        director_nolan = DirectorModel(name="Christopher Nolan")
        session.add(director_nolan)
        await session.flush()

        inception = MovieModel(
            name="Inception",
            year=2010,
            imdb=8.8,
            price=9.99,
            time=148,
            votes=1309038,
            meta_score=74,
            gross=836800000,
            description="A thief who steals corporate secrets through "
                        "use of dream-sharing technology is given the inverse "
                        "task of planting an idea into the mind of a CEO.",
            certification_id=certification.id,
            genres=[genre_action, genre_scifi],
            stars=[star_dicaprio],
            directors=[director_nolan],
        )

        dark_knight = MovieModel(
            name="The Dark Knight",
            year=2008,
            imdb=9.0,
            price=9.99,
            time=152,
            votes=2900000,
            meta_score=84,
            gross=1006000000,
            description="When the menace known as the Joker wreaks havoc "
                        "and chaos on the people of Gotham, the caped crusader"
                        " must come to terms with one of the greatest psychological "
                        "tests of his ability to fight injustice.",
            certification_id=certification.id,
            genres=[genre_crime, genre_drama],
            stars=[star_bale, star_ledger],
            directors=[director_nolan],
        )

        session.add_all([inception, dark_knight])
        await session.commit()

