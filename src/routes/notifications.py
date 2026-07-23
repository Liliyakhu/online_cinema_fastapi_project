from typing import List

from fastapi import APIRouter, Depends

from config.dependencies import get_current_user_id, get_notification_service
from schemas import NotificationSchema, MessageResponseSchema
from services.notifications import NotificationService

router = APIRouter()


@router.get(
    "/",
    response_model=List[NotificationSchema],
    summary="Get all notifications for the current user",
)
async def get_notifications(
    user_id: int = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> List[NotificationSchema]:
    return await service.get_notifications(user_id)


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
    user_id: int = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> MessageResponseSchema:
    return await service.mark_as_read(notification_id, user_id)
