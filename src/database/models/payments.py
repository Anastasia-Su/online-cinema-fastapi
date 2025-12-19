from enum import Enum as PyEnum
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Enum as SQLEnum,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import relationship, mapped_column
from src.database import Base


class PaymentStatusEnum(str, PyEnum):
    SUCCESSFUL = "successful"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class PaymentModel(Base):
    __tablename__ = "payments"

    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(ForeignKey("users.id"), nullable=False)
    order_id = mapped_column(ForeignKey("orders.id"), nullable=False)

    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    status = mapped_column(
        SQLEnum(PaymentStatusEnum, name="payment_status_enum",),
        
        default=PaymentStatusEnum.SUCCESSFUL,
        nullable=False,
    )

    amount = mapped_column(Numeric(10, 2), nullable=False)

    external_payment_id = mapped_column(String, nullable=True)

    user = relationship("UserModel")
    order = relationship("OrderModel")
    items = relationship(
        "PaymentItemModel",
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaymentItemModel(Base):
    __tablename__ = "payment_items"

    id = mapped_column(Integer, primary_key=True)
    payment_id = mapped_column(ForeignKey("payments.id"), nullable=False)
    order_item_id = mapped_column(ForeignKey("order_items.id"), nullable=False)

    price_at_payment = mapped_column(Numeric(10, 2), nullable=False)

    payment = relationship("PaymentModel", back_populates="items")
    order_item = relationship("OrderItemModel")