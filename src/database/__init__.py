import os

from src.database.models.base import Base
from src.database.models.accounts import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserProfileModel
)
from src.database.models.movies import (
    MovieModel,
    DirectorModel,
    StarModel,
    GenreModel,
    CertificationModel,
    MovieDirectorModel,
    MovieStarModel,
    MovieGenreModel
)
# from database.session_sqlite import reset_sqlite_database as reset_database
from src.database.validators import accounts as accounts_validators

# environment = os.getenv("ENVIRONMENT", "developing")

# if environment == "testing":
#     from database.session_sqlite import (
#         get_sqlite_db_contextmanager as get_db_contextmanager,
#         get_sqlite_db as get_db
#     )
# else:
from src.database.session_db import (
    get_db_contextmanager,
    get_db,
    AsyncSessionLocal,
    sync_engine,
)
