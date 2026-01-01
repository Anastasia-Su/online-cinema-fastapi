from enum import Enum
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Enum as SQLEnum,
    Numeric,
    func,
)
from sqlalchemy.orm import relationship
from src.database import Base


# from src.database.models.user import UserModel


class OrderStatusEnum(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    CANCELED = "canceled"


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status = Column(
        SQLEnum(OrderStatusEnum, name="order_status"),
        nullable=False,
        default=OrderStatusEnum.PENDING,
    )
    total_amount = Column(Numeric(10, 2), nullable=True)

    # relationships
    user = relationship("UserModel", back_populates="orders")
    items = relationship(
        "OrderItemModel",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id = Column(
        Integer,
        ForeignKey("movies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price_at_order = Column(Numeric(10, 2), nullable=False)

    # relationships
    order = relationship("OrderModel", back_populates="items")
    movie = relationship("MovieModel")
