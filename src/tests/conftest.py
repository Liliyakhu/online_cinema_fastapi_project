import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config.dependencies import get_settings, get_accounts_email_notificator, get_s3_storage_client
from database import (
    UserGroupEnum,
    UserGroupModel,
    get_db_contextmanager,
)
from database.session_sqlite import reset_sqlite_database
from main import app
from security.token_manager import JWTAuthManager
from security.interfaces import JWTAuthManagerInterface
from tests.doubles.stubs.emails import StubEmailSender
from tests.doubles.fakes.storage import FakeS3Storage


@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    await reset_sqlite_database()
    yield


@pytest_asyncio.fixture
async def email_sender_stub():
    return StubEmailSender()


@pytest_asyncio.fixture
async def s3_storage_fake():
    return FakeS3Storage()


@pytest_asyncio.fixture
async def client(email_sender_stub, s3_storage_fake):
    app.dependency_overrides[get_accounts_email_notificator] = lambda: email_sender_stub
    app.dependency_overrides[get_s3_storage_client] = lambda: s3_storage_fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session():
    async with get_db_contextmanager() as session:
        yield session


@pytest_asyncio.fixture
async def jwt_manager() -> JWTAuthManagerInterface:
    settings = get_settings()
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )


@pytest_asyncio.fixture
async def seed_user_groups(db_session: AsyncSession):
    groups = [{"name": group.value} for group in UserGroupEnum]
    await db_session.execute(insert(UserGroupModel).values(groups))
    await db_session.commit()
    yield db_session
