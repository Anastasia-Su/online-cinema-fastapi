from typing import Optional
from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Boolean,
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
)
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.database import Base


class MovieRatingModel(Base):
    __tablename__ = "movie_ratings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–10
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )


class MovieCommentModel(Base):
    __tablename__ = "movie_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("movie_comments.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    replies: Mapped[list["MovieCommentModel"]] = relationship(
        "MovieCommentModel", back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped[Optional["MovieCommentModel"]] = relationship(
        "MovieCommentModel", remote_side=[id], back_populates="replies"
    )

    liked_by_users: Mapped[list["UserModel"]] = relationship(
        "UserModel", secondary="CommentLikeModel", lazy="raise"
    )


class NotificationModel(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(50))  # comment_reply, comment_like
    related_id: Mapped[int]  # comment_id or like_id
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())


UserFavoriteMovieModel = Table(
    "user_favorite_movies",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("movie_id", ForeignKey("movies.id"), primary_key=True),
    UniqueConstraint("user_id", "movie_id"),
)

CommentLikeModel = Table(
    "comment_likes",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "comment_id",
        ForeignKey("movie_comments.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    UniqueConstraint("user_id", "comment_id"),
)

MovieLikeModel = Table(
    "movie_likes",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("like", Boolean, nullable=False, default=True),
    UniqueConstraint("user_id", "movie_id"),
)
