from typing import Optional, Annotated
from datetime import date
from decimal import Decimal
from fastapi import HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from src.database import profile_validators, PaymentStatusEnum


class PaymentItemResponseSchema(BaseModel):
    id: int
    order_item_id: int
    price_at_payment: Decimal

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class PaymentResponseSchema(BaseModel):
    id: int
    created_at: datetime
    status: PaymentStatusEnum
    amount: Decimal
    order_id: int
    external_payment_id: str | None
    items: list[PaymentItemResponseSchema]

    model_config: ConfigDict = ConfigDict(from_attributes=True)


class PaymentListSchema(BaseModel):
    id: int
    created_at: datetime
    status: PaymentStatusEnum
    amount: Decimal
    order_id: int

    model_config: ConfigDict = ConfigDict(from_attributes=True)
