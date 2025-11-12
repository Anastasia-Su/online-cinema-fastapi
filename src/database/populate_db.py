import asyncio
import random
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, insert

from src.database import (
    AsyncSessionLocal,
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
    UserGroupModel,
    UserGroupEnum
    
)


fake = Faker()

NUM_MOVIES = 10_000  # number of movies to add


async def seed_movies():
    async with AsyncSessionLocal() as session:
        # ✅ Keep existing data — just reuse it
        certifications = (await session.execute(select(CertificationModel))).scalars().all()
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
                    "Action", "Adventure", "Comedy", "Drama", "Horror",
                    "Romance", "Sci-Fi", "Thriller", "Fantasy", "Animation"
                ]
            ]
            session.add_all(genres)
            await session.flush()

        if not stars:
            stars = [StarModel(name=fake.name()) for _ in range(20)]
            session.add_all(stars)
            await session.flush()

        if not directors:
            directors = [DirectorModel(name=fake.name()) for _ in range(10)]
            session.add_all(directors)
            await session.flush()

        # --- Create new movies ---
        movies = []
        for _ in range(NUM_MOVIES):
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
        await session.commit()
        print(f"✅ Added {len(movies)} new movies successfully!")
        
        
async def seed_user_groups() -> None:
    """
    Seed the UserGroupModel table with default user groups if none exist.

    This method checks whether any user groups are already present in the database.
    If no records are found, it inserts all groups defined in the UserGroupEnum.
    After insertion, the changes are flushed to the current transaction.
    """
    async with AsyncSessionLocal() as session:
        count_stmt = select(func.count(UserGroupModel.id))
        result = await session.execute(count_stmt)
        existing_groups = result.scalar()

        if existing_groups == 0:
            groups = [{"name": group.value} for group in UserGroupEnum]
            await session.execute(insert(UserGroupModel).values(groups))
            await session.flush()
            await session.commit()

            print("User groups seeded successfully.")


if __name__ == "__main__":
    # asyncio.run(seed_movies())
    asyncio.run(seed_user_groups())

