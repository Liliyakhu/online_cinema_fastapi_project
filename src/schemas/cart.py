from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CartItemSchema(BaseModel):
    movie_id: int
    title: str
    price: float
    genres: List[str]
    year: int
    added_at: datetime

    model_config = {"from_attributes": True}


class CartResponseSchema(BaseModel):
    items: List[CartItemSchema]
    total_items: int
    total_price: float

