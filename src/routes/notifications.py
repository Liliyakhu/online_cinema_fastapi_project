from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import get_db
from database.models import NotificationModel
from schemas import NotificationSchema, MessageResponseSchema
from config.dependencies import get_current_user_id

router = APIRouter()


@router.get(
    "/",
    response_model=List[NotificationSchema],
    summary="Get all notifications for the current user",
)
async def get_notifications(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> List[NotificationSchema]:
    result = await db.execute(
        select(NotificationModel)
        .where(NotificationModel.user_id == user_id)
        .order_by(NotificationModel.created_at.desc())
    )
    notifications = result.scalars().all()

    return [NotificationSchema.model_validate(n) for n in notifications]


@router.patch(
    "/{notification_id}/read/",
    response_model=MessageResponseSchema,
    summary="Mark a notification as read",
    responses={
        404: {
            "description": "Notification not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Notification not found."}
                }
            },
        },
    }
)
async def mark_notification_read(
        notification_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    notification = await db.get(NotificationModel, notification_id)
    if not notification or notification.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found.")

    notification.is_read = True
    await db.commit()

    return MessageResponseSchema(message="Notification marked as read.")