from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.models.accounts import UserModel, UserGroupEnum
from database.models.cart import CartModel, CartItemModel
from database.models.movies import MovieModel
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from notifications.interfaces import EmailSenderInterface
from schemas import OrderResponseSchema, OrderItemSchema, MessageResponseSchema


class OrderService:

    def __init__(self, db: AsyncSession, email_sender: EmailSenderInterface):
        self.db = db
        self.email_sender = email_sender

    async def _is_movie_purchased(self, user_id: int, movie_id: int) -> bool:
        result = await self.db.execute(
            select(OrderItemModel)
            .join(OrderModel)
            .where(
                OrderItemModel.movie_id == movie_id,
                OrderModel.user_id == user_id,
                OrderModel.status == OrderStatusEnum.PAID,
            )
        )
        return result.scalars().first() is not None

    async def _get_or_create_cart(self, user_id: int) -> CartModel:
        result = await self.db.execute(
            select(CartModel).where(CartModel.user_id == user_id)
        )
        cart = result.scalars().first()
        if not cart:
            cart = CartModel(user_id=user_id)
            self.db.add(cart)
            await self.db.flush()
        return cart

    def _build_order_response(self, order: OrderModel) -> OrderResponseSchema:
        return OrderResponseSchema(
            id=order.id,
            created_at=order.created_at,
            status=order.status,
            total_amount=order.total_amount,
            items=[
                OrderItemSchema(
                    movie_id=item.movie_id,
                    title=item.movie.name,
                    price_at_order=item.price_at_order,
                )
                for item in order.items
            ],
        )

    async def create_order(self, user_id: int) -> OrderResponseSchema:
        cart = await self._get_or_create_cart(user_id)

        result = await self.db.execute(
            select(CartItemModel)
            .where(CartItemModel.cart_id == cart.id)
            .options(joinedload(CartItemModel.movie))
        )
        cart_items = result.unique().scalars().all()

        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty.")

        valid_items = []
        excluded_movies = []

        for cart_item in cart_items:
            movie = cart_item.movie
            if not movie:
                excluded_movies.append(f"Movie ID {cart_item.movie_id} (no longer available)")
                continue
            if await self._is_movie_purchased(user_id, movie.id):
                excluded_movies.append(f"{movie.name} (already purchased)")
                continue
            valid_items.append(cart_item)

        if not valid_items:
            raise HTTPException(
                status_code=400,
                detail=f"No valid movies to order. Excluded: {', '.join(excluded_movies)}"
            )

        total_amount = sum(item.movie.price for item in valid_items)
        order = OrderModel(
            user_id=user_id,
            status=OrderStatusEnum.PENDING,
            total_amount=total_amount,
        )
        self.db.add(order)
        await self.db.flush()

        for cart_item in valid_items:
            self.db.add(OrderItemModel(
                order_id=order.id,
                movie_id=cart_item.movie.id,
                price_at_order=cart_item.movie.price,
            ))
            await self.db.delete(cart_item)

        await self.db.commit()

        result = await self.db.execute(
            select(OrderModel)
            .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
            .filter_by(id=order.id)
        )
        order = result.unique().scalar_one()
        return self._build_order_response(order)

    async def get_orders(self, user_id: int) -> List[OrderResponseSchema]:
        result = await self.db.execute(
            select(OrderModel)
            .where(OrderModel.user_id == user_id)
            .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
            .order_by(OrderModel.created_at.desc())
        )
        orders = result.unique().scalars().all()
        return [self._build_order_response(order) for order in orders]

    async def get_order(self, order_id: int, user_id: int) -> OrderResponseSchema:
        result = await self.db.execute(
            select(OrderModel)
            .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
            .filter_by(id=order_id)
        )
        order = result.unique().scalar_one_or_none()
        if not order or order.user_id != user_id:
            raise HTTPException(status_code=404, detail="Order not found.")
        return self._build_order_response(order)

    async def cancel_order(self, order_id: int, user_id: int) -> MessageResponseSchema:
        order = await self.db.get(OrderModel, order_id)
        if not order or order.user_id != user_id:
            raise HTTPException(status_code=404, detail="Order not found.")
        if order.status != OrderStatusEnum.PENDING:
            raise HTTPException(status_code=409, detail="Only pending orders can be canceled.")
        order.status = OrderStatusEnum.CANCELED
        await self.db.commit()
        return MessageResponseSchema(message="Order canceled successfully.")

    async def pay_order(self, order_id: int, user_id: int) -> MessageResponseSchema:
        order = await self.db.get(OrderModel, order_id)
        if not order or order.user_id != user_id:
            raise HTTPException(status_code=404, detail="Order not found.")
        if order.status != OrderStatusEnum.PENDING:
            raise HTTPException(status_code=409, detail="Only pending orders can be paid.")

        order.status = OrderStatusEnum.PAID
        await self.db.commit()

        user = await self.db.get(UserModel, user_id)
        await self.email_sender.send_order_confirmation_email(
            email=user.email,
            order_id=order.id,
            total_amount=str(order.total_amount),
        )
        return MessageResponseSchema(message="Order paid successfully.")

    async def get_all_orders(
        self,
        current_user_id: int,
        user_id_filter: Optional[int] = None,
        status_filter: Optional[OrderStatusEnum] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[OrderResponseSchema]:
        result = await self.db.execute(
            select(UserModel).options(joinedload(UserModel.group)).filter_by(id=current_user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
        ):
            raise HTTPException(status_code=403, detail="No permission.")

        stmt = select(OrderModel).options(
            joinedload(OrderModel.items).joinedload(OrderItemModel.movie)
        )
        if user_id_filter:
            stmt = stmt.where(OrderModel.user_id == user_id_filter)
        if status_filter:
            stmt = stmt.where(OrderModel.status == status_filter)
        if date_from:
            stmt = stmt.where(OrderModel.created_at >= date_from)
        if date_to:
            stmt = stmt.where(OrderModel.created_at <= date_to)
        stmt = stmt.order_by(OrderModel.created_at.desc())

        result = await self.db.execute(stmt)
        orders = result.unique().scalars().all()
        return [self._build_order_response(order) for order in orders]
