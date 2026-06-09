import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete

from celery_app import celery_app
from database.models.accounts import ActivationTokenModel, PasswordResetTokenModel
from database.session_sqlite import AsyncSQLiteSessionLocal


async def _delete_expired_tokens():
    """
    Async function to delete expired activation and password reset tokens.
    """
    async with AsyncSQLiteSessionLocal() as session:
        now = datetime.now(timezone.utc)

        await session.execute(
            delete(ActivationTokenModel).where(
                ActivationTokenModel.expires_at < now
            )
        )

        await session.execute(
            delete(PasswordResetTokenModel).where(
                PasswordResetTokenModel.expires_at < now
            )
        )

        await session.commit()


@celery_app.task
def delete_expired_tokens():
    """
    Celery task to delete expired tokens.
    Runs the async function synchronously using asyncio.run().
    """
    asyncio.run(_delete_expired_tokens())
