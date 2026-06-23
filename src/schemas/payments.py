from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from database.models.payments import PaymentStatusEnum


class CheckoutSessionResponseSchema(BaseModel):
    checkout_url: str


class PaymentResponseSchema(BaseModel):
    id: int
    order_id: int
    created_at: datetime
    status: PaymentStatusEnum
    amount: Decimal
    external_payment_id: Optional[str]

    model_config = {"from_attributes": True}
