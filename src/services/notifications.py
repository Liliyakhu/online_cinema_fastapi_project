from typing import List

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NotificationModel
from schemas import NotificationSchema, MessageResponseSchema


class NotificationService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_notifications(self, user_id: int) -> List[NotificationSchema]:
        result = await self.db.execute(
            select(NotificationModel)
            .where(NotificationModel.user_id == user_id)
            .order_by(NotificationModel.created_at.desc())
        )
        notifications = result.scalars().all()
        return [NotificationSchema.model_validate(n) for n in notifications]

    async def mark_as_read(self, notification_id: int, user_id: int) -> MessageResponseSchema:
        notification = await self.db.get(NotificationModel, notification_id)
        if not notification or notification.user_id != user_id:
            raise HTTPException(status_code=404, detail="Notification not found.")

        notification.is_read = True
        await self.db.commit()
        return MessageResponseSchema(message="Notification marked as read.")