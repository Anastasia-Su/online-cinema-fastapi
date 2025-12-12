
import os

ENV = os.getenv("ENVIRONMENT", "testing")

import asyncio
import random
from faker import Faker
from sqlalchemy import select, func, insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db_contextmanager

from src.database import (
    # AsyncSessionLocal,
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
    UserGroupModel,
    UserGroupEnum,
)


if ENV == "testing":
    from src.database.session_sqlite import AsyncSQLiteSessionLocal, get_sqlite_db

    AsyncSessionLocal = AsyncSQLiteSessionLocal
    get_db = get_sqlite_db
else:
    from src.database.session_db import AsyncSessionLocal as AsyncPostgresSessionLocal, get_db as get_postgres_db

    AsyncSessionLocal = AsyncPostgresSessionLocal
    get_db = get_postgres_db


fake = Faker()

NUM_MOVIES = 10_000  # number of movies to add


async def seed_movies(session: AsyncSession, num_movies=NUM_MOVIES):
    
    # ✅ Keep existing data — just reuse it
    certifications = (
        (await session.execute(select(CertificationModel))).scalars().all()
    )
    genres = (await session.execute(select(GenreModel))).scalars().all()
    stars = (await session.execute(select(StarModel))).scalars().all()
    directors = (await session.execute(select(DirectorModel))).scalars().all()

    # ✅ If reference tables are empty, seed them
    if not certifications:
        certifications = [
            CertificationModel(name=name)
            for name in ["G", "PG", "PG-13", "R", "NC-17"]
        ]
        session.add_all(certifications)
        await session.flush()

    if not genres:
        genres = [
            GenreModel(name=name)
            for name in [
                "Action",
                "Adventure",
                "Comedy",
                "Drama",
                "Horror",
                "Romance",
                "Sci-Fi",
                "Thriller",
                "Fantasy",
                "Animation",
            ]
        ]
        session.add_all(genres)
        await session.flush()

    # if not stars:
    #     stars = [StarModel(name=fake.name()) for _ in range(20)]
    #     session.add_all(stars)
    #     await session.flush()
    existing_star_names = {s.name for s in stars}
    new_stars = []
    while len(new_stars) < 20:
        name = fake.unique.name()
        if name not in existing_star_names:
            new_stars.append(StarModel(name=name))
            existing_star_names.add(name)
    session.add_all(new_stars)
    await session.flush()
    stars.extend(new_stars)

    # if not directors:
    #     directors = [DirectorModel(name=fake.name()) for _ in range(10)]
    #     session.add_all(directors)
    #     await session.flush()
    existing_director_names = {d.name for d in directors}
    new_directors = []
    while len(new_directors) < 10:
        name = fake.unique.name()
        if name not in existing_director_names:
            new_directors.append(DirectorModel(name=name))
            existing_director_names.add(name)
    session.add_all(new_directors)
    await session.flush()
    directors.extend(new_directors)

    # --- Create new movies ---
    movies = []
    for _ in range(num_movies):
        certification = random.choice(certifications)
        movie_genres = random.sample(genres, k=random.randint(1, 3))
        movie_stars = random.sample(stars, k=random.randint(2, 5))
        movie_directors = random.sample(directors, k=random.randint(1, 2))

        movie = MovieModel(
            name=fake.sentence(nb_words=3).rstrip("."),
            year=random.randint(1980, 2025),
            time=random.randint(80, 180),
            imdb=round(random.uniform(5.0, 9.8), 1),
            votes=random.randint(10_000, 2_000_000),
            meta_score=round(random.uniform(50, 100), 1),
            gross=round(random.uniform(10_000_000, 900_000_000), 2),
            description=fake.paragraph(nb_sentences=3),
            price=round(random.uniform(3.99, 19.99), 2),
            certification=certification,
            genres=movie_genres,
            stars=movie_stars,
            directors=movie_directors,
        )

        movies.append(movie)

    session.add_all(movies)
    
    print(f"✅ Added {len(movies)} new movies successfully!")


async def seed_user_groups(session: AsyncSession) -> None:
    """
    Seed the UserGroupModel table with default user groups if none exist.

    This method checks whether any user groups are already present in the database.
    If no records are found, it inserts all groups defined in the UserGroupEnum.
    After insertion, the changes are flushed to the current transaction.
    """
    
    count_stmt = select(func.count(UserGroupModel.id))
    result = await session.execute(count_stmt)
    existing_groups = result.scalar()

    if existing_groups == 0:
        groups = [{"name": group.value} for group in UserGroupEnum]
        await session.execute(insert(UserGroupModel).values(groups))
        await session.flush()
        

        print("User groups seeded successfully.")


# if __name__ == "__main__":
#     # asyncio.run(seed_movies())
#     asyncio.run(seed_user_groups())
# async def seed_users():
#     from sqlalchemy import select
#     from src.database.models.accounts import UserModel, UserGroupModel

#     async with get_db_contextmanager() as db:
#         groups = (await db.execute(select(UserGroupModel))).scalars().all()
#         group_map = {g.name.value: g.id for g in groups}

#         users = [
#             UserModel.create(
#                 email="admin@test.com",
#                 raw_password="Password1!",
#                 group_id=group_map["admin"]
#             ),
#             UserModel.create(
#                 email="mod@test.com",
#                 raw_password="Password1!",
#                 group_id=group_map["moderator"]
#             ),
#             UserModel.create(
#                 email="user@test.com",
#                 raw_password="Password1!",
#                 group_id=group_map["user"]
#             ),
#         ]

#         # All users must be active for testing
#         for u in users:
#             u.is_active = True

#         db.add_all(users)
        # await db.commit()

async def seed_users(session: AsyncSession):
    from src.database.models.accounts import UserModel, UserGroupModel
    from sqlalchemy import select

    # Fetch groups using the SAME session that just created them
    
    groups = (await session.execute(select(UserGroupModel))).scalars().all()
    group_map = {g.name.value: g.id for g in groups}

    # Make sure we have all groups (they were just seeded)
    if len(group_map) < 3:
        raise RuntimeError("User groups not seeded properly!")

    users = [
        UserModel.create(
            email="admin@test.com",
            raw_password="Password1!",
            group_id=group_map["admin"]
        ),
        UserModel.create(
            email="mod@test.com",
            raw_password="Password2!",
            group_id=group_map["moderator"]
        ),
        UserModel.create(
            email="user@test.com",
            raw_password="Password3!",
            group_id=group_map["user"]
        ),
    ]

    session.add_all(users)
    await session.flush()

# async def seed_users():
#     from src.database.models.accounts import UserModel, UserGroupModel
#     from sqlalchemy import select

#     # Fetch groups using the SAME session that just created them
#     async with AsyncSessionLocal() as session:
#         groups = (await session.execute(select(UserGroupModel))).scalars().all()
#         group_map = {g.name.value: g.id for g in groups}

#         # Make sure we have all groups (they were just seeded)
#         if len(group_map) < 3:
#             raise RuntimeError("User groups not seeded properly!")

#         users = [
#             UserModel.create(
#                 email="admin@test.com",
#                 raw_password="Password1!",
#                 group_id=group_map["admin"]
#             ),
#             UserModel.create(
#                 email="mod@test.com",
#                 raw_password="Password2!",
#                 group_id=group_map["moderator"]
#             ),
#             UserModel.create(
#                 email="user@test.com",
#                 raw_password="Password3!",
#                 group_id=group_map["user"]
#             ),
#         ]

#         session.add_all(users)
#         session.commit()
    
async def seed_certifications(session: AsyncSession):
    from src.database import CertificationModel   # adjust path
    from sqlalchemy import insert, select

    count = (await session.execute(select(func.count()).select_from(CertificationModel))).scalar_one()
    if count == 0:
        await session.execute(insert(CertificationModel).values([
            {"id": 1, "name": "G"},
            {"id": 2, "name": "PG"},
            {"id": 3, "name": "PG-13"},
            {"id": 4, "name": "R"},
        ]))


def make_token(user, jwt_manager):
    access = jwt_manager.create_access_token({"user_id": user.id})
    return {"Authorization": f"Bearer {access}"}

