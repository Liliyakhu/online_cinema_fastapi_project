import stripe
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional, Literal, List


from database import get_db, UserModel, UserGroupEnum
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from database.models.payments import PaymentModel, PaymentItemModel, PaymentStatusEnum

from config.dependencies import get_current_user_id, get_settings
from notifications.interfaces import EmailSenderInterface
from config.dependencies import get_accounts_email_notificator
from schemas import CheckoutSessionResponseSchema, PaymentResponseSchema

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


@router.get(
    "/",
    response_model=List[PaymentResponseSchema],
    summary="Get current user's payment history",
)
async def get_payments(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> List[PaymentResponseSchema]:
    result = await db.execute(
        select(PaymentModel)
        .where(PaymentModel.user_id == user_id)
        .order_by(PaymentModel.created_at.desc())
    )
    payments = result.scalars().all()

    return [PaymentResponseSchema.model_validate(payment) for payment in payments]


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
        user_id_filter: Optional[int] = Query(None, description="Filter by user ID"),
        status_filter: Optional[PaymentStatusEnum] = Query(None, description="Filter by payment status"),
        date_from: Optional[datetime] = Query(None, description="Filter payments created after this date"),
        date_to: Optional[datetime] = Query(None, description="Filter payments created before this date"),
        db: AsyncSession = Depends(get_db),
        current_user_id: int = Depends(get_current_user_id),
) -> List[PaymentResponseSchema]:
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=current_user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    stmt = select(PaymentModel)

    if user_id_filter:
        stmt = stmt.where(PaymentModel.user_id == user_id_filter)

    if status_filter:
        stmt = stmt.where(PaymentModel.status == status_filter)

    if date_from:
        stmt = stmt.where(PaymentModel.created_at >= date_from)

    if date_to:
        stmt = stmt.where(PaymentModel.created_at <= date_to)

    stmt = stmt.order_by(PaymentModel.created_at.desc())

    result = await db.execute(stmt)
    payments = result.scalars().all()

    return [PaymentResponseSchema.model_validate(payment) for payment in payments]