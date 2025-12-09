import uuid as uuid_lib
from typing import Optional
from datetime import datetime

# AT THE VERY END OF THE FILE WHERE CertificationModel IS DEFINED


from sqlalchemy import (
    String,
    Integer,
    Float,
    Text,
    DECIMAL,
    UniqueConstraint,
    Date,
    ForeignKey,
    Table,
    Column,
    Index,
    func,
    select,
    and_,
    column,
)
from sqlalchemy.orm import mapped_column, Mapped, relationship, column_property
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import text
from src.database import Base


MovieGenreModel = Table(
    "movie_genres",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Index("idx_movie_genres_movie_id", "movie_id"),
    Index("idx_movie_genres_genre_id", "genre_id"),
)

MovieStarModel = Table(
    "movie_stars",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "star_id",
        ForeignKey("stars.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Index("idx_movie_stars_movie_id", "movie_id"),
)

MovieDirectorModel = Table(
    "movie_directors",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "director_id",
        ForeignKey("directors.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Index("idx_movie_directors_movie_id", "movie_id"),
)


class GenreModel(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel", secondary=MovieGenreModel, back_populates="genres"
    )

    __table_args__ = (
        Index(
            "idx_genres_name_trgm",
            func.lower(name),
            postgresql_using="gin",
            postgresql_ops={"lower(name)": "gin_trgm_ops"},
        ),
    )

    def __repr__(self):
        return f"<Genre(name='{self.name}')>"


class StarModel(Base):
    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel", secondary=MovieStarModel, back_populates="stars"
    )

    def __repr__(self):
        return f"<Star(name='{self.name}')>"


class DirectorModel(Base):
    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel", secondary=MovieDirectorModel, back_populates="directors"
    )

    def __repr__(self):
        return f"<Director(name='{self.name}')>"


class CertificationModel(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel", back_populates="certification", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Certification(name='{self.name}')>"


class MovieModel(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid_lib.uuid4()), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    time: Mapped[int] = mapped_column(Integer, nullable=False)  # duration in minutes
    imdb: Mapped[float] = mapped_column(Float, nullable=False)
    votes: Mapped[int] = mapped_column(Integer, nullable=False)
    meta_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)

    certification_id: Mapped[int] = mapped_column(
        ForeignKey("certifications.id", ondelete="CASCADE"), nullable=False
    )

    certification: Mapped["CertificationModel"] = relationship(
        "CertificationModel", back_populates="movies"
    )

    genres: Mapped[list["GenreModel"]] = relationship(
        "GenreModel", secondary=MovieGenreModel, back_populates="movies"
    )

    stars: Mapped[list["StarModel"]] = relationship(
        "StarModel", secondary=MovieStarModel, back_populates="movies"
    )

    directors: Mapped[list["DirectorModel"]] = relationship(
        "DirectorModel", secondary=MovieDirectorModel, back_populates="movies"
    )

    favorited_by_users: Mapped[list["UserModel"]] = relationship(
        "UserModel",
        secondary="user_favorite_movies",
        back_populates="favorite_movies",
    )

    liked_by_users: Mapped[list["UserModel"]] = relationship(
        "UserModel",
        secondary="movie_likes",
        back_populates="liked_movies",
    )

    ratings: Mapped[list["MovieRatingModel"]] = relationship(
        "MovieRatingModel",
        back_populates="movie",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    rating_average: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True
    )
    like_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True
    )
    favorite_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True
    )
    comment_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True
    )

    __table_args__ = (
        UniqueConstraint("name", "year", "time", name="unique_movie_constraint"),
        Index(
            "idx_movies_name_trgm",
            func.lower(name),
            postgresql_using="gin",
            postgresql_ops={"lower(name)": "gin_trgm_ops"},
        ),
        Index("idx_movies_year", "year"),
        Index("idx_movies_imdb", "imdb"),
        Index("idx_movies_price", "price"),
    )

    def __repr__(self):
        return (
            f"<Movie(name='{self.name}', year={self.year}, "
            f"time={self.time}, imdb={self.imdb}, certification_id={self.certification_id})>"
        )
