from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from src.schemas.movies import MovieListItemSchema

from datetime import datetime
from src.database import OrderStatusEnum


class OrderItemResponseSchema(BaseModel):
    id: int
    movie: MovieListItemSchema
    price_at_order: Decimal

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class OrderResponseSchema(BaseModel):
    id: int
    user_id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal
    items: list[OrderItemResponseSchema]

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class OrderListResponseSchema(BaseModel):
    id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Decimal

    model_config: ConfigDict = ConfigDict(from_attributes=True)
