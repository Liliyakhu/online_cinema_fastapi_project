from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from database.models.orders import OrderStatusEnum


class OrderItemSchema(BaseModel):
    movie_id: int
    title: str
    price_at_order: Decimal

    model_config = {"from_attributes": True}


class OrderResponseSchema(BaseModel):
    id: int
    created_at: datetime
    status: OrderStatusEnum
    total_amount: Optional[Decimal]
    items: List[OrderItemSchema]

    model_config = {"from_attributes": True}


class OrderListResponseSchema(BaseModel):
    orders: List[OrderResponseSchema]
