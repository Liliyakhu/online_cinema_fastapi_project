from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from config.dependencies import get_settings
from database.models.base import Base
from database.models.accounts import UserGroupModel, UserGroupEnum


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