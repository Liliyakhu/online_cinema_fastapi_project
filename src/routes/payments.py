from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from config.dependencies import get_current_user_id, get_payment_service
from database.models.payments import PaymentStatusEnum
from schemas import CheckoutSessionResponseSchema, PaymentResponseSchema
from services.payments import PaymentService

router = APIRouter()


@router.post(
    "/orders/{order_id}/checkout/",
    response_model=CheckoutSessionResponseSchema,
    summary="Create a Stripe checkout session for an order",
    responses={
        404: {
            "description": "Order not found.",
            "content": {"application/json": {"example": {"detail": "Order not found."}}},
        },
        409: {
            "description": "Order is not pending.",
            "content": {"application/json": {"example": {"detail": "Order is not pending."}}},
        },
    }
)
async def create_checkout_session(
    order_id: int,
    user_id: int = Depends(get_current_user_id),
    service: PaymentService = Depends(get_payment_service),
) -> CheckoutSessionResponseSchema:
    return await service.create_checkout_session(order_id, user_id)


@router.post("/webhook/", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    service: PaymentService = Depends(get_payment_service),
):
    return await service.handle_webhook(request)


@router.get(
    "/",
    response_model=List[PaymentResponseSchema],
    summary="Get current user's payment history",
)
async def get_payments(
    user_id: int = Depends(get_current_user_id),
    service: PaymentService = Depends(get_payment_service),
) -> List[PaymentResponseSchema]:
    return await service.get_payments(user_id)


@router.get(
    "/all/",
    response_model=List[PaymentResponseSchema],
    summary="Moderator: get all payments with filters",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
    }
)
async def get_all_payments(
    user_id_filter: Optional[int] = Query(None),
    status_filter: Optional[PaymentStatusEnum] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user_id: int = Depends(get_current_user_id),
    service: PaymentService = Depends(get_payment_service),
) -> List[PaymentResponseSchema]:
    return await service.get_all_payments(
        current_user_id, user_id_filter, status_filter, date_from, date_to
    )


@router.get("/success/", response_class=HTMLResponse, include_in_schema=False)
async def payment_success_page():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>Payment Successful</title></head>
    <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
        <h1 style="color: #27ae60;">✅ Payment Successful!</h1>
        <p>Thank you for your purchase. A confirmation email has been sent to you.</p>
        <p>You can now access your purchased movies in your account.</p>
    </body>
    </html>
    """


@router.get("/cancel/", response_class=HTMLResponse, include_in_schema=False)
async def payment_cancel_page():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>Payment Canceled</title></head>
    <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
        <h1 style="color: #e74c3c;">❌ Payment Canceled</h1>
        <p>Your payment was not completed. You can try again from your cart.</p>
    </body>
    </html>
    """
