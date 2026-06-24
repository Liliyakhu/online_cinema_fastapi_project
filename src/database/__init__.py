import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "developing")

if ENVIRONMENT in ("docker", "production"):
    from database.session_postgresql import get_db, get_db_contextmanager
else:
    from database.session_sqlite import get_db, get_db_contextmanager

from database.models.base import Base
from database.models.accounts import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserProfileModel
)
from database.models.movies import (
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
)