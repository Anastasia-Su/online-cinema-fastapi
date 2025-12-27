import random
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from faker import Faker
from sqlalchemy import select, func, insert

from src.database import (
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
    UserGroupModel,
    UserGroupEnum,
    UserModel,
    OrderStatusEnum,
    OrderModel,
    OrderItemModel,
)

import os

ENV = os.getenv("ENVIRONMENT", "testing")


if ENV == "testing":
    from src.database.session_sqlite import AsyncSQLiteSessionLocal, get_sqlite_db

    AsyncSessionLocal = AsyncSQLiteSessionLocal
    get_db = get_sqlite_db
else:
    from src.database.session_db import (
        AsyncSessionLocal as AsyncPostgresSessionLocal,
        get_db as get_postgres_db,
    )

    AsyncSessionLocal = AsyncPostgresSessionLocal
    get_db = get_postgres_db


fake = Faker()

NUM_MOVIES = 10_000  # number of movies to add


async def seed_movies(session: AsyncSession, num_movies: int = NUM_MOVIES) -> None:
    certifications = (await session.execute(select(CertificationModel))).scalars().all()
    genres = (await session.execute(select(GenreModel))).scalars().all()
    stars = (await session.execute(select(StarModel))).scalars().all()
    directors = (await session.execute(select(DirectorModel))).scalars().all()

    if not certifications:
        certifications = [
            CertificationModel(name=name) for name in ["G", "PG", "PG-13", "R", "NC-17"]
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


async def seed_users(session: AsyncSession) -> None:
    from src.database.models.accounts import UserModel, UserGroupModel
    from sqlalchemy import select

    # Fetch groups using the SAME session that just created them

    groups = (await session.execute(select(UserGroupModel))).scalars().all()
    group_map = {g.name.value: g.id for g in groups}

    # Make sure we have all groups (they were just seeded)
    if len(group_map) < 3:
        raise RuntimeError("User groups not seeded properly!")

    existing_emails = set(
        (await session.execute(select(UserModel.email))).scalars().all()
    )

    users = [
        UserModel.create(
            email="admin@test.com",
            raw_password="Password1!",
            group_id=group_map["admin"],
        ),
        UserModel.create(
            email="mod@test.com",
            raw_password="Password2!",
            group_id=group_map["moderator"],
        ),
        UserModel.create(
            email="user@test.com", raw_password="Password3!", group_id=group_map["user"]
        ),
    ]

    # session.add_all(users)
    for user in users:
        if user.email not in existing_emails:
            session.add(user)
    await session.flush()


async def seed_orders(session: AsyncSession) -> None:
    """
    Minimal orders seeding for payment tests.
    """

    user = (
        await session.execute(
            select(UserModel).where(UserModel.email == "user@test.com")
        )
    ).scalar_one()

    movies = (await session.execute(select(MovieModel).limit(3))).scalars().all()

    if len(movies) < 2:
        raise RuntimeError("Need at least 2 movies for order seeding")

    # --------------------
    # PENDING ORDER
    # --------------------
    pending_order = OrderModel(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=Decimal("0.00"),
    )
    session.add(pending_order)
    await session.flush()

    total = Decimal("0.00")
    for movie in movies[:2]:
        price = Decimal(str(movie.price))
        total += price

        session.add(
            OrderItemModel(
                order_id=pending_order.id,
                movie_id=movie.id,
                price_at_order=price,
            )
        )

    pending_order.total_amount = total

    # --------------------
    # PAID ORDER
    # --------------------
    paid_order = OrderModel(
        user_id=user.id,
        status=OrderStatusEnum.PAID,
        total_amount=Decimal("0.00"),
    )
    session.add(paid_order)
    await session.flush()

    movie = movies[2]
    price = Decimal(str(movie.price))

    session.add(
        OrderItemModel(
            order_id=paid_order.id,
            movie_id=movie.id,
            price_at_order=price,
        )
    )

    paid_order.total_amount = price

    await session.flush()

    print("✅ Seeded 1 PENDING and 1 PAID order")


# def make_token(user, jwt_manager):
#     access = jwt_manager.create_access_token({"user_id": user.id})
#     return {"Authorization": f"Bearer {access}"}
