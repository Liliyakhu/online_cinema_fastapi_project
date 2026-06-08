import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


from config.settings import Settings, TestingSettings
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager

from notifications.emails import EmailSender
from notifications.interfaces import EmailSenderInterface

security = HTTPBearer()


def get_settings() -> Settings:
    environment = os.getenv("ENVIRONMENT", "developing")
    if environment == "testing":
        return TestingSettings()
    return Settings()


def get_jwt_auth_manager(
    settings: Settings = Depends(get_settings)
) -> JWTAuthManagerInterface:
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )


def get_accounts_email_notificator(
    settings: Settings = Depends(get_settings)
) -> EmailSenderInterface:
    return EmailSender(
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        email=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        template_dir=settings.PATH_TO_EMAIL_TEMPLATES_DIR,
        activation_email_template_name=settings.ACTIVATION_EMAIL_TEMPLATE_NAME,
        activation_complete_email_template_name=settings.ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME,
        password_email_template_name=settings.PASSWORD_RESET_TEMPLATE_NAME,
        password_complete_email_template_name=settings.PASSWORD_RESET_COMPLETE_TEMPLATE_NAME,
    )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> int:
    try:
        payload = jwt_manager.decode_access_token(credentials.credentials)
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
        return user_id
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
