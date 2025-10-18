import asyncio
import random
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.database.models.movies import (
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
)

fake = Faker()

NUM_MOVIES = 100  # number of movies to create


async def seed_movies():
    async with AsyncSessionLocal() as session: 
        # Skip if already seeded
        existing = await session.execute(select(MovieModel))
        if existing.scalars().first():
            print("⚠️ Database already seeded with movies.")
            return

        # --- Create reference data ---
        certifications = [
            CertificationModel(name=name)
            for name in ["G", "PG", "PG-13", "R", "NC-17"]
        ]
        genres = [
            GenreModel(name=name)
            for name in [
                "Action", "Adventure", "Comedy", "Drama", "Horror",
                "Romance", "Sci-Fi", "Thriller", "Fantasy", "Animation"
            ]
        ]
        stars = [StarModel(name=fake.name()) for _ in range(20)]
        directors = [DirectorModel(name=fake.name()) for _ in range(10)]

        session.add_all(certifications + genres + stars + directors)
        await session.flush()  # ensure they get IDs before linking

        # --- Create movies ---
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
        print(f"✅ Seeded {len(movies)} movies successfully!")


if __name__ == "__main__":
    asyncio.run(seed_movies())
