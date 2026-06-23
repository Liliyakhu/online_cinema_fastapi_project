import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import get_db, UserModel
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from database.models.payments import PaymentModel, PaymentItemModel, PaymentStatusEnum

from config.dependencies import get_current_user_id, get_settings
from notifications.interfaces import EmailSenderInterface
from config.dependencies import get_accounts_email_notificator
from schemas import CheckoutSessionResponseSchema

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
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
        settings=Depends(get_settings),
) -> CheckoutSessionResponseSchema:
    stripe.api_key = settings.STRIPE_SECRET_KEY

    result = await db.execute(
        select(OrderModel)
        .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
        .filter_by(id=order_id)
    )
    order = result.unique().scalar_one_or_none()

    if not order or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(status_code=409, detail="Order is not pending.")

    line_items = [
        {
            "price_data": {
                "currency": "usd",
                "product_data": {"name": item.movie.name},
                "unit_amount": int(item.price_at_order * 100),
            },
            "quantity": 1,
        }
        for item in order.items
    ]

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=line_items,
        mode="payment",
        success_url="http://localhost:8000/api/v1/payments/success/",
        cancel_url="http://localhost:8000/api/v1/payments/cancel/",
        metadata={"order_id": str(order.id), "user_id": str(user_id)},
    )

    return CheckoutSessionResponseSchema(checkout_url=session.url)


@router.post("/webhook/", include_in_schema=False)
async def stripe_webhook(
        request: Request,
        db: AsyncSession = Depends(get_db),
        settings=Depends(get_settings),
        email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = int(session["metadata"]["order_id"])
        user_id = int(session["metadata"]["user_id"])

        result = await db.execute(
            select(OrderModel)
            .options(joinedload(OrderModel.items))
            .filter_by(id=order_id)
        )
        order = result.unique().scalar_one_or_none()

        if order and order.status == OrderStatusEnum.PENDING:
            order.status = OrderStatusEnum.PAID

            payment = PaymentModel(
                user_id=user_id,
                order_id=order.id,
                amount=order.total_amount,
                status=PaymentStatusEnum.SUCCESSFUL,
                external_payment_id=session.payment_intent,
            )
            db.add(payment)
            await db.flush()

            for order_item in order.items:
                payment_item = PaymentItemModel(
                    payment_id=payment.id,
                    order_item_id=order_item.id,
                    price_at_payment=order_item.price_at_order,
                )
                db.add(payment_item)

            await db.commit()

            user = await db.get(UserModel, user_id)
            await email_sender.send_order_confirmation_email(
                email=user.email,
                order_id=order.id,
                total_amount=str(order.total_amount),
            )

    return {"status": "success"}
