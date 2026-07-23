from fastapi import APIRouter, Depends, Request, status

from config.dependencies import get_current_user_id, get_profile_service
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from services.profiles import ProfileService

router = APIRouter()


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    summary="Create user profile",
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id),
    profile_data: ProfileCreateSchema = Depends(ProfileCreateSchema.from_form),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponseSchema:
    return await service.create_profile(user_id, current_user_id, profile_data)


@router.get(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    summary="Get user profile",
    responses={
        404: {
            "description": "Profile not found.",
            "content": {"application/json": {"example": {"detail": "Profile not found."}}},
        },
    }
)
async def get_profile(
    user_id: int,
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponseSchema:
    return await service.get_profile(user_id)


@router.patch(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    summary="Update user profile",
)
async def update_profile(
    user_id: int,
    request: Request,
    current_user_id: int = Depends(get_current_user_id),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileResponseSchema:
    return await service.update_profile(user_id, current_user_id, request)
