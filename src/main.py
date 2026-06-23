from contextlib import asynccontextmanager
from fastapi import FastAPI
from database.session_sqlite import (
    init_db,
    close_db,
    create_default_groups,
    create_test_users, create_test_movies
)
from routes.accounts import router as accounts_router
from routes.movies import router as movies_router
from routes.notifications import router as notifications_router
from routes.cart import router as cart_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await create_default_groups()
    await create_test_users()
    await create_test_movies()
    yield
    await close_db()

app = FastAPI(
    title="Online cinema",
    description="Description of project",
    lifespan=lifespan
)

api_version_prefix = "/api/v1"

app.include_router(accounts_router, prefix=f"{api_version_prefix}/accounts", tags=["Accounts"])
app.include_router(movies_router, prefix=f"{api_version_prefix}/cinema", tags=["Cinema"])
app.include_router(notifications_router, prefix=f"{api_version_prefix}/notifications", tags=["Notifications"])
app.include_router(cart_router, prefix=f"{api_version_prefix}/cart", tags=["Cart"])

