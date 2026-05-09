from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(
    title="Online cinema",
    description="Description of project",
    lifespan=lifespan
)

api_version_prefix = "/api/v1"
