import logging
import stripe
from datetime import datetime
from typing import Optional, List

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.settings import Settings
from database.models.accounts import UserModel, UserGroupEnum
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from database.models.payments import PaymentModel, PaymentItemModel, PaymentStatusEnum
from notifications.interfaces import EmailSenderInterface
from schemas import CheckoutSessionResponseSchema, PaymentResponseSchema


class PaymentService:

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        email_sender: EmailSenderInterface,
    ):
        self.db = db
        self.settings = settings
        self.email_sender = email_sender

    async def create_checkout_session(
        self, order_id: int, user_id: int
    ) -> CheckoutSessionResponseSchema:
        stripe.api_key = self.settings.STRIPE_SECRET_KEY

        result = await self.db.execute(
            select(OrderModel)
            .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
            .filter_by(id=order_id)
        )
        order = result.unique().scalar_one_or_none()

        if not order or order.user_id != user_id:
            raise HTTPException(status_code=404, detail="Order not found.")

        if order.status != OrderStatusEnum.PENDING:
            raise HTTPException(status_code=409, detail="Order is not pending.")

        current_total = sum(item.movie.price for item in order.items)
        price_changed = current_total != order.total_amount
        old_total = order.total_amount

        if price_changed:
            order.total_amount = current_total
            await self.db.commit()

        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": item.movie.name},
                    "unit_amount": int(item.movie.price * 100),
                },
                "quantity": 1,
            }
            for item in order.items
        ]

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=f"{self.settings.BASE_URL}/api/v1/payments/success/",
            cancel_url=f"{self.settings.BASE_URL}/api/v1/payments/cancel/",
            metadata={"order_id": str(order.id), "user_id": str(user_id)},
        )

        warning = None
        if price_changed:
            warning = f"Note: total price has changed from ${old_total} to ${current_total} due to price updates."

        return CheckoutSessionResponseSchema(
            checkout_url=session.url,
            price_changed_warning=warning,
        )

    async def handle_webhook(self, request: Request) -> dict:
        stripe.api_key = self.settings.STRIPE_SECRET_KEY
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            raise HTTPException(status_code=400, detail="Invalid webhook signature.")

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            order_id = int(session["metadata"]["order_id"])
            user_id = int(session["metadata"]["user_id"])

            result = await self.db.execute(
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
                self.db.add(payment)
                await self.db.flush()

                for order_item in order.items:
                    self.db.add(PaymentItemModel(
                        payment_id=payment.id,
                        order_item_id=order_item.id,
                        price_at_payment=order_item.price_at_order,
                    ))

                await self.db.commit()

                user = await self.db.get(UserModel, user_id)
                await self.email_sender.send_order_confirmation_email(
                    email=user.email,
                    order_id=order.id,
                    total_amount=str(order.total_amount),
                )

        elif event["type"] == "payment_intent.payment_failed":
            payment_intent = event["data"]["object"]
            last_error = payment_intent.last_payment_error
            error_message = last_error.message if last_error else "Unknown error"
            logging.warning(
                f"Payment failed: {error_message}. "
                f"Recommendation: Try a different payment method or contact your bank."
            )

        return {"status": "success"}

    async def get_payments(self, user_id: int) -> List[PaymentResponseSchema]:
        result = await self.db.execute(
            select(PaymentModel)
            .where(PaymentModel.user_id == user_id)
            .order_by(PaymentModel.created_at.desc())
        )
        payments = result.scalars().all()
        return [PaymentResponseSchema.model_validate(p) for p in payments]

    async def get_all_payments(
        self,
        current_user_id: int,
        user_id_filter: Optional[int] = None,
        status_filter: Optional[PaymentStatusEnum] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[PaymentResponseSchema]:
        result = await self.db.execute(
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

        result = await self.db.execute(stmt)
        payments = result.scalars().all()
        return [PaymentResponseSchema.model_validate(p) for p in payments]
