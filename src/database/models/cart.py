from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import relationship
from src.database import Base


class CartModel(Base):
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    user = relationship("UserModel", back_populates="cart")
    items = relationship(
        "CartItemModel",
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CartItemModel(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(
        Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    movie_id = Column(
        Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    cart = relationship("CartModel", back_populates="items")
    movie = relationship("MovieModel")

    __table_args__ = (UniqueConstraint("cart_id", "movie_id", name="uq_cart_movie"),)
