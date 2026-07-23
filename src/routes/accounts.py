from fastapi import APIRouter, Depends, status

from config.dependencies import (
    get_current_user_id,
    get_account_service,
)
from services.accounts import AccountService
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

router = APIRouter()


@router.post(
    "/register/",
    response_model=UserRegistrationResponseSchema,
    summary="User Registration",
    description="Register a new user with an email and password.",
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "Conflict - User with this email already exists.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "A user with this email test@example.com already exists."
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during user creation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred during user creation."
                    }
                }
            },
        },
    }
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> UserRegistrationResponseSchema:
    return await service.register(user_data)


@router.post(
    "/activate/",
    response_model=MessageResponseSchema,
    summary="Activate User Account",
    description="Activate a user's account using their email and activation token.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - The activation token is invalid or expired, "
                           "or the user account is already active.",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_token": {
                            "summary": "Invalid Token",
                            "value": {
                                "detail": "Invalid or expired activation token."
                            }
                        },
                        "already_active": {
                            "summary": "Account Already Active",
                            "value": {
                                "detail": "User account is already active."
                            }
                        },
                    }
                }
            },
        },
    },
)
async def activate_account(
    activation_data: UserActivationRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> MessageResponseSchema:
    return await service.activate(activation_data)


@router.post(
    "/login/",
    response_model=UserLoginResponseSchema,
    summary="User Login",
    description="Authenticate a user and return access and refresh tokens.",
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {
            "description": "Unauthorized - Invalid email or password.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid email or password."
                    }
                }
            },
        },
        403: {
            "description": "Forbidden - User account is not activated.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "User account is not activated."
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred while processing the request.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while processing the request."
                    }
                }
            },
        },
    },
)
async def login_user(
    login_data: UserLoginRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> UserLoginResponseSchema:
    return await service.login(login_data)


@router.post(
    "/refresh/",
    response_model=TokenRefreshResponseSchema,
    summary="Refresh Access Token",
    description="Refresh the access token using a valid refresh token.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - The provided refresh token is invalid or expired.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Token has expired."
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized - Refresh token not found.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Refresh token not found."
                    }
                }
            },
        },
        404: {
            "description": "Not Found - The user associated with the token does not exist.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "User not found."
                    }
                }
            },
        },
    },
)
async def refresh_access_token(
    token_data: TokenRefreshRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> TokenRefreshResponseSchema:
    return await service.refresh_token(token_data)


@router.post(
    "/logout/",
    response_model=MessageResponseSchema,
    summary="User Logout",
    description="Logout a user by invalidating their refresh token.",
    status_code=status.HTTP_200_OK,
)
async def logout_user(
    token_data: TokenRefreshRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> MessageResponseSchema:
    return await service.logout(token_data)


@router.post(
    "/password-reset/request/",
    response_model=MessageResponseSchema,
    summary="Request Password Reset Token",
    description=(
            "Allows a user to request a password reset token. If the user exists and is active, "
            "a new token will be generated and any existing tokens will be invalidated."
    ),
    status_code=status.HTTP_200_OK,
)
async def request_password_reset_token(
    data: PasswordResetRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> MessageResponseSchema:
    return await service.request_password_reset(data)


@router.post(
    "/reset-password/complete/",
    response_model=MessageResponseSchema,
    summary="Reset User Password",
    description="Reset a user's password if a valid token is provided.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - Invalid email or token.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid email or token."}
                }
            },
        },
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while resetting the password."}
                }
            },
        },
    },
)
async def reset_password(
    data: PasswordResetCompleteRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> MessageResponseSchema:
    return await service.reset_password(data)


@router.post(
    "/resend-activation/",
    response_model=MessageResponseSchema,
    summary="Resend Activation Email",
    description="Resend activation email to a user.",
    status_code=status.HTTP_200_OK,
    responses={
        400: {
            "description": "Bad Request - User account is already active.",
            "content": {
                "application/json": {
                    "examples": {
                        "already_active": {
                            "summary": "Account Already Active",
                            "value": {
                                "detail": "User account is already active."
                            }
                        },
                    }
                }
            },
        },
    },
)
async def resend_activation_email(
    data: PasswordResetRequestSchema,
    service: AccountService = Depends(get_account_service),
) -> MessageResponseSchema:
    return await service.resend_activation(data)


@router.post(
    "/change-password/",
    response_model=MessageResponseSchema,
    summary="Change Password",
    description="Change user password if the old password is correct.",
    status_code=status.HTTP_200_OK,
    responses={
        401: {
            "description": "Unauthorized - Invalid old password.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid old password."}
                }
            },
        },
        404: {
            "description": "Not Found - User not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "User not found."}
                }
            },
        },
        500: {
            "description": "Internal Server Error.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while changing the password."}
                }
            },
        },
    },
)
async def change_password(
    data: ChangePasswordRequestSchema,
    service: AccountService = Depends(get_account_service),
    user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    return await service.change_password(data, user_id)


@router.patch(
    "/users/{user_id}/activate/",
    response_model=MessageResponseSchema,
    summary="Manually Activate User",
    description="Admin can manually activate a user account.",
    status_code=status.HTTP_200_OK,
    responses={
        403: {
            "description": "Forbidden - Only admins can perform this action.",
            "content": {
                "application/json": {
                    "example": {"detail": "You do not have permission to perform this action."}
                }
            },
        },
        404: {
            "description": "Not Found - User not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "User not found."}
                }
            },
        },
    },
)
async def activate_user_by_admin(
    user_id: int,
    service: AccountService = Depends(get_account_service),
    current_user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    return await service.activate_user_by_admin(user_id, current_user_id)


@router.patch(
    "/users/{user_id}/group/",
    response_model=MessageResponseSchema,
    summary="Change User Group",
    description="Admin can change a user's group.",
    status_code=status.HTTP_200_OK,
    responses={
        403: {
            "description": "Forbidden - Only admins can perform this action.",
            "content": {
                "application/json": {
                    "example": {"detail": "You do not have permission to perform this action."}
                }
            },
        },
        404: {
            "description": "Not Found - User or group not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "User not found."}
                }
            },
        },
    },
)
async def change_user_group(
    user_id: int,
    data: UserGroupUpdateSchema,
    service: AccountService = Depends(get_account_service),
    current_user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    return await service.change_user_group(user_id, data, current_user_id)
