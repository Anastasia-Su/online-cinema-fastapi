import os

from src.database.models.base import Base
from src.database.models.accounts import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserProfileModel,
    GenderEnum
)
from src.database.models.movies.movies_base import (
    MovieModel,
    DirectorModel,
    StarModel,
    GenreModel,
    CertificationModel,
    MovieDirectorModel,
    MovieStarModel,
    MovieGenreModel
)
from src.database.models.movies.movies_actions import (
    UserFavoriteMovieModel,
    MovieLikeModel
)
from src.database.validators import accounts as accounts_validators
from src.database.validators import profiles as profile_validators

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
    get_current_user,
    # get_settings,
    AsyncSessionLocal,
    sync_engine,
)
