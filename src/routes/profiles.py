from typing import cast
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.dependencies import get_s3_storage_client, get_current_user_id
from database import get_db, UserModel, UserGroupEnum
from database.models.accounts import UserProfileModel, GenderEnum
from exceptions import S3FileUploadError
from schemas.profiles import (
    ProfileCreateSchema,
    ProfileResponseSchema,
    ProfileUpdateSchema
)
from validation import (
    validate_name,
    validate_gender,
    validate_birth_date,
    validate_image
)

from storages import S3StorageInterface


router = APIRouter()


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    summary="Create user profile",
    status_code=status.HTTP_201_CREATED
)
async def create_profile(
        user_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
        profile_data: ProfileCreateSchema = Depends(ProfileCreateSchema.from_form)
) -> ProfileResponseSchema:

    if user_id != current_user_id:
        result = await db.execute(
            select(UserModel).options(joinedload(UserModel.group)).filter_by(id=current_user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not (
                current_user.has_group(UserGroupEnum.MODERATOR) or
                current_user.has_group(UserGroupEnum.ADMIN)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this profile."
            )

    user = await db.get(UserModel, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not active."
        )

    stmt_profile = select(UserProfileModel).where(UserProfileModel.user_id == user.id)
    result_profile = await db.execute(stmt_profile)
    existing_profile = result_profile.scalars().first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile."
        )

    avatar_bytes = await profile_data.avatar.read()
    avatar_key = f"avatars/{user.id}_{profile_data.avatar.filename}"

    try:
        await s3_client.upload_file(file_name=avatar_key, file_data=avatar_bytes)
    except S3FileUploadError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )

    new_profile = UserProfileModel(
        user_id=cast(int, user.id),
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=cast(GenderEnum, profile_data.gender),
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key
    )

    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    avatar_url = await s3_client.get_file_url(new_profile.avatar)

    return ProfileResponseSchema(
        id=new_profile.id,
        user_id=new_profile.user_id,
        first_name=new_profile.first_name,
        last_name=new_profile.last_name,
        gender=new_profile.gender,
        date_of_birth=new_profile.date_of_birth,
        info=new_profile.info,
        avatar=cast(HttpUrl, avatar_url)
    )


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
        db: AsyncSession = Depends(get_db),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
) -> ProfileResponseSchema:
    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    avatar_url = await s3_client.get_file_url(profile.avatar)

    return ProfileResponseSchema(
        id=profile.id,
        user_id=profile.user_id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        gender=profile.gender,
        date_of_birth=profile.date_of_birth,
        info=profile.info,
        avatar=cast(HttpUrl, avatar_url)
    )


@router.patch(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    summary="Update user profile",
)
async def update_profile(
        user_id: int,
        request: Request,
        current_user_id: int = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
) -> ProfileResponseSchema:
    if user_id != current_user_id:
        result = await db.execute(
            select(UserModel).options(joinedload(UserModel.group)).filter_by(id=current_user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not (
                current_user.has_group(UserGroupEnum.MODERATOR) or
                current_user.has_group(UserGroupEnum.ADMIN)
        ):
            raise HTTPException(status_code=403, detail="No permission.")

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    form = await request.form()

    if "first_name" in form:
        value = form.get("first_name")
        if value:
            try:
                validate_name(value)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            profile.first_name = value.lower()
        else:
            profile.first_name = None

    if "last_name" in form:
        value = form.get("last_name")
        if value:
            try:
                validate_name(value)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            profile.last_name = value.lower()
        else:
            profile.last_name = None

    if "gender" in form:
        value = form.get("gender")
        if value:
            try:
                validate_gender(value)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            profile.gender = value
        else:
            profile.gender = None

    if "date_of_birth" in form:
        value = form.get("date_of_birth")
        if value:
            try:
                parsed_date = date.fromisoformat(value)
                validate_birth_date(parsed_date)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            profile.date_of_birth = parsed_date
        else:
            profile.date_of_birth = None

    if "info" in form:
        value = form.get("info")
        profile.info = value if value else None

    avatar = form.get("avatar")
    if avatar is not None and hasattr(avatar, "filename") and avatar.filename:
        try:
            validate_image(avatar)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        old_avatar_key = profile.avatar
        avatar_bytes = await avatar.read()
        new_avatar_key = f"avatars/{user_id}_{avatar.filename}"

        try:
            await s3_client.upload_file(file_name=new_avatar_key, file_data=avatar_bytes)
            if old_avatar_key:
                await s3_client.delete_file(old_avatar_key)
        except S3FileUploadError:
            raise HTTPException(status_code=500, detail="Failed to upload avatar.")

        profile.avatar = new_avatar_key

    await db.commit()
    await db.refresh(profile)

    avatar_url = await s3_client.get_file_url(profile.avatar)

    return ProfileResponseSchema(
        id=profile.id,
        user_id=profile.user_id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        gender=profile.gender,
        date_of_birth=profile.date_of_birth,
        info=profile.info,
        avatar=cast(HttpUrl, avatar_url)
    )
