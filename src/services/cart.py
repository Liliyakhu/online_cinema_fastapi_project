from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.models.cart import CartModel, CartItemModel
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from database.models.movies import MovieModel
from database.models.accounts import UserModel, UserGroupEnum
from schemas import CartItemSchema, CartResponseSchema, MessageResponseSchema


class CartService:

    def __init__(self, db: AsyncSession):
        self.db = db

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

    async def _build_cart_response(self, cart_items) -> CartResponseSchema:
        items = [
            CartItemSchema(
                movie_id=item.movie.id,
                title=item.movie.name,
                price=float(item.movie.price),
                genres=[genre.name for genre in item.movie.genres],
                year=item.movie.year,
                added_at=item.added_at,
            )
            for item in cart_items
        ]
        total_price = sum(item.price for item in items)
        return CartResponseSchema(
            items=items,
            total_items=len(items),
            total_price=total_price,
        )

    async def add_item(self, user_id: int, movie_id: int) -> MessageResponseSchema:
        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        if await self._is_movie_purchased(user_id, movie_id):
            raise HTTPException(
                status_code=409,
                detail="Movie already purchased. Repeat purchases are not allowed."
            )

        cart = await self._get_or_create_cart(user_id)

        existing = await self.db.execute(
            select(CartItemModel).where(
                CartItemModel.cart_id == cart.id,
                CartItemModel.movie_id == movie_id,
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail="Movie already in cart.")

        self.db.add(CartItemModel(cart_id=cart.id, movie_id=movie_id))
        await self.db.commit()
        return MessageResponseSchema(message="Movie added to cart.")

    async def remove_item(self, user_id: int, movie_id: int) -> MessageResponseSchema:
        cart = await self._get_or_create_cart(user_id)

        result = await self.db.execute(
            select(CartItemModel).where(
                CartItemModel.cart_id == cart.id,
                CartItemModel.movie_id == movie_id,
            )
        )
        cart_item = result.scalars().first()
        if not cart_item:
            raise HTTPException(status_code=404, detail="Movie not found in cart.")

        await self.db.delete(cart_item)
        await self.db.commit()
        return MessageResponseSchema(message="Movie removed from cart.")

    async def get_cart(self, user_id: int) -> CartResponseSchema:
        cart = await self._get_or_create_cart(user_id)
        await self.db.commit()

        result = await self.db.execute(
            select(CartItemModel)
            .where(CartItemModel.cart_id == cart.id)
            .options(
                joinedload(CartItemModel.movie).joinedload(MovieModel.genres)
            )
        )
        cart_items = result.unique().scalars().all()
        return await self._build_cart_response(cart_items)

    async def clear_cart(self, user_id: int) -> MessageResponseSchema:
        cart = await self._get_or_create_cart(user_id)
        await self.db.execute(
            CartItemModel.__table__.delete().where(CartItemModel.cart_id == cart.id)
        )
        await self.db.commit()
        return MessageResponseSchema(message="Cart cleared successfully.")

    async def get_user_cart_by_moderator(
        self, user_id: int, current_user_id: int
    ) -> CartResponseSchema:
        result = await self.db.execute(
            select(UserModel).options(joinedload(UserModel.group)).filter_by(id=current_user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
        ):
            raise HTTPException(status_code=403, detail="No permission.")

        cart_result = await self.db.execute(
            select(CartModel).where(CartModel.user_id == user_id)
        )
        cart = cart_result.scalars().first()
        if not cart:
            raise HTTPException(status_code=404, detail="Cart not found.")

        items_result = await self.db.execute(
            select(CartItemModel)
            .where(CartItemModel.cart_id == cart.id)
            .options(joinedload(CartItemModel.movie).joinedload(MovieModel.genres))
        )
        cart_items = items_result.unique().scalars().all()
        return await self._build_cart_response(cart_items)
