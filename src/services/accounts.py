from datetime import datetime, timezone
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.settings import Settings
from database import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    ActivationTokenModel,
    RefreshTokenModel,
    PasswordResetTokenModel,
)
from exceptions import BaseSecurityError
from notifications.interfaces import EmailSenderInterface
from schemas import (
    UserRegistrationRequestSchema,
    UserRegistrationResponseSchema,
    MessageResponseSchema,
    UserActivationRequestSchema,
    UserLoginRequestSchema,
    UserLoginResponseSchema,
    TokenRefreshRequestSchema,
    TokenRefreshResponseSchema,
    PasswordResetRequestSchema,
    PasswordResetCompleteRequestSchema,
    ChangePasswordRequestSchema,
    UserGroupUpdateSchema,
)
from security.interfaces import JWTAuthManagerInterface


class AccountService:

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        jwt_manager: JWTAuthManagerInterface,
        email_sender: EmailSenderInterface,
    ):
        self.db = db
        self.settings = settings
        self.jwt_manager = jwt_manager
        self.email_sender = email_sender

    async def register(
        self, user_data: UserRegistrationRequestSchema
    ) -> UserRegistrationResponseSchema:
        stmt = select(UserModel).where(UserModel.email == user_data.email)
        result = await self.db.execute(stmt)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A user with this email {user_data.email} already exists."
            )

        stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
        result = await self.db.execute(stmt)
        user_group = result.scalars().first()
        if not user_group:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default user group not found."
            )

        try:
            new_user = UserModel.create(
                email=str(user_data.email),
                raw_password=user_data.password,
                group_id=user_group.id,
            )
            self.db.add(new_user)
            await self.db.flush()

            activation_token = ActivationTokenModel(user_id=new_user.id)
            self.db.add(activation_token)
            await self.db.flush()

            await self.db.commit()
            await self.db.refresh(new_user)
            await self.db.refresh(activation_token)
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred during user creation."
            ) from e

        activation_link = (
            f"{self.settings.BASE_URL}/api/v1/accounts/activate/"
            f"?email={new_user.email}&token={activation_token.token}"
        )
        await self.email_sender.send_activation_email(new_user.email, activation_link)
        return UserRegistrationResponseSchema.model_validate(new_user)

    async def activate(
        self, activation_data: UserActivationRequestSchema
    ) -> MessageResponseSchema:
        stmt = (
            select(ActivationTokenModel)
            .options(joinedload(ActivationTokenModel.user))
            .join(UserModel)
            .where(
                UserModel.email == activation_data.email,
                ActivationTokenModel.token == activation_data.token,
            )
        )
        result = await self.db.execute(stmt)
        token_record = result.scalars().first()

        now_utc = datetime.now(timezone.utc)
        if not token_record or cast(datetime, token_record.expires_at).replace(tzinfo=timezone.utc) < now_utc:
            if token_record:
                await self.db.delete(token_record)
                await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired activation token."
            )

        user = token_record.user
        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account is already active."
            )

        user.is_active = True
        await self.db.delete(token_record)
        await self.db.commit()

        login_link = f"{self.settings.BASE_URL}/api/v1/accounts/login/"
        await self.email_sender.send_activation_complete_email(
            str(activation_data.email), login_link
        )
        return MessageResponseSchema(message="User account activated successfully.")

    async def login(
        self, login_data: UserLoginRequestSchema
    ) -> UserLoginResponseSchema:
        stmt = select(UserModel).filter_by(email=login_data.email)
        result = await self.db.execute(stmt)
        user = result.scalars().first()

        if not user or not user.verify_password(login_data.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not activated.",
            )

        jwt_refresh_token = self.jwt_manager.create_refresh_token({"user_id": user.id})

        try:
            refresh_token = RefreshTokenModel.create(
                user_id=user.id,
                days_valid=self.settings.LOGIN_TIME_DAYS,
                token=jwt_refresh_token,
            )
            self.db.add(refresh_token)
            await self.db.flush()
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while processing the request.",
            )

        jwt_access_token = self.jwt_manager.create_access_token({"user_id": user.id})
        return UserLoginResponseSchema(
            access_token=jwt_access_token,
            refresh_token=jwt_refresh_token,
        )

    async def refresh_token(
        self, token_data: TokenRefreshRequestSchema
    ) -> TokenRefreshResponseSchema:
        try:
            decoded_token = self.jwt_manager.decode_refresh_token(token_data.refresh_token)
            user_id = decoded_token.get("user_id")
        except BaseSecurityError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            )

        stmt = select(RefreshTokenModel).filter_by(token=token_data.refresh_token)
        result = await self.db.execute(stmt)
        if not result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found.",
            )

        stmt = select(UserModel).filter_by(id=user_id)
        result = await self.db.execute(stmt)
        if not result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        new_access_token = self.jwt_manager.create_access_token({"user_id": user_id})
        return TokenRefreshResponseSchema(access_token=new_access_token)

    async def logout(
        self, token_data: TokenRefreshRequestSchema
    ) -> MessageResponseSchema:
        try:
            self.jwt_manager.verify_refresh_token_or_raise(token_data.refresh_token)
        except BaseSecurityError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            )

        stmt = select(RefreshTokenModel).filter_by(token=token_data.refresh_token)
        result = await self.db.execute(stmt)
        refresh_token_record = result.scalars().first()
        if not refresh_token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found.",
            )

        await self.db.delete(refresh_token_record)
        await self.db.commit()
        return MessageResponseSchema(message="Successfully logged out.")

    async def request_password_reset(
        self, data: PasswordResetRequestSchema
    ) -> MessageResponseSchema:
        stmt = select(UserModel).filter_by(email=data.email)
        result = await self.db.execute(stmt)
        user = result.scalars().first()

        if not user or not user.is_active:
            return MessageResponseSchema(
                message="If you are registered, you will receive an email with instructions."
            )

        await self.db.execute(
            delete(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user.id)
        )

        reset_token = PasswordResetTokenModel(user_id=cast(int, user.id))
        self.db.add(reset_token)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(reset_token)

        password_reset_link = (
            f"{self.settings.BASE_URL}/api/v1/accounts/reset-password/complete/"
            f"?email={user.email}&token={reset_token.token}"
        )
        await self.email_sender.send_password_reset_email(str(data.email), password_reset_link)

        return MessageResponseSchema(
            message="If you are registered, you will receive an email with instructions."
        )

    async def reset_password(
        self, data: PasswordResetCompleteRequestSchema
    ) -> MessageResponseSchema:
        stmt = select(UserModel).filter_by(email=data.email)
        result = await self.db.execute(stmt)
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or token."
            )

        stmt = select(PasswordResetTokenModel).filter_by(user_id=user.id)
        result = await self.db.execute(stmt)
        token_record = result.scalars().first()

        if not token_record or token_record.token != data.token:
            if token_record:
                await self.db.delete(token_record)
                await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or token."
            )

        expires_at = cast(datetime, token_record.expires_at).replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            await self.db.delete(token_record)
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or token."
            )

        try:
            user.password = data.password
            await self.db.delete(token_record)
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while resetting the password."
            )

        login_link = f"{self.settings.BASE_URL}/api/v1/accounts/login/"
        await self.email_sender.send_password_reset_complete_email(str(data.email), login_link)
        return MessageResponseSchema(message="Password reset successfully.")

    async def resend_activation(
        self, data: PasswordResetRequestSchema
    ) -> MessageResponseSchema:
        stmt = select(UserModel).filter_by(email=data.email)
        result = await self.db.execute(stmt)
        user = result.scalars().first()

        if not user:
            return MessageResponseSchema(
                message="If your email is registered, you will receive an activation link."
            )

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account is already active."
            )

        await self.db.execute(
            delete(ActivationTokenModel).where(ActivationTokenModel.user_id == user.id)
        )

        new_token = ActivationTokenModel(user_id=cast(int, user.id))
        self.db.add(new_token)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(new_token)

        activation_link = (
            f"{self.settings.BASE_URL}/api/v1/accounts/activate/"
            f"?email={user.email}&token={new_token.token}"
        )
        await self.email_sender.send_activation_email(str(data.email), activation_link)
        return MessageResponseSchema(
            message="If your email is registered, you will receive an activation link."
        )

    async def change_password(
        self, data: ChangePasswordRequestSchema, user_id: int
    ) -> MessageResponseSchema:
        result = await self.db.execute(select(UserModel).filter_by(id=user_id))
        current_user = result.scalars().first()
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        if not current_user.verify_password(data.old_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid old password.",
            )

        try:
            current_user.password = data.new_password
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while changing the password.",
            )

        return MessageResponseSchema(message="Password changed successfully.")

    async def activate_user_by_admin(
        self, user_id: int, current_user_id: int
    ) -> MessageResponseSchema:
        result = await self.db.execute(
            select(UserModel)
            .options(joinedload(UserModel.group))
            .filter_by(id=current_user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not current_user.has_group(UserGroupEnum.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        result = await self.db.execute(select(UserModel).filter_by(id=user_id))
        target_user = result.scalars().first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        target_user.is_active = True
        await self.db.commit()
        return MessageResponseSchema(message="User account activated successfully.")

    async def change_user_group(
        self, user_id: int, data: UserGroupUpdateSchema, current_user_id: int
    ) -> MessageResponseSchema:
        result = await self.db.execute(
            select(UserModel)
            .options(joinedload(UserModel.group))
            .filter_by(id=current_user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not current_user.has_group(UserGroupEnum.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        result = await self.db.execute(select(UserModel).filter_by(id=user_id))
        target_user = result.scalars().first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        result = await self.db.execute(
            select(UserGroupModel).where(UserGroupModel.name == data.group)
        )
        group = result.scalars().first()
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found.",
            )

        target_user.group_id = group.id
        await self.db.commit()
        return MessageResponseSchema(message=f"User group changed to {data.group.value} successfully.")
