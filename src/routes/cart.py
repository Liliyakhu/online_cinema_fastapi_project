from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import get_db, MovieModel
from database.models import (
    CartModel,
    CartItemModel,
    UserModel,
    UserGroupEnum,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum
)
from schemas import CartItemSchema, CartResponseSchema, MessageResponseSchema
from config.dependencies import get_current_user_id

router = APIRouter()


async def is_movie_purchased(db: AsyncSession, user_id: int, movie_id: int) -> bool:
    """
    Check if the user has already purchased this movie.
    """
    result = await db.execute(
        select(OrderItemModel)
        .join(OrderModel)
        .where(
            OrderItemModel.movie_id == movie_id,
            OrderModel.user_id == user_id,
            OrderModel.status == OrderStatusEnum.PAID,
        )
    )
    return result.scalars().first() is not None


async def get_or_create_cart(db: AsyncSession, user_id: int) -> CartModel:
    """Get the user's cart, creating one if it doesn't exist yet."""
    result = await db.execute(select(CartModel).where(CartModel.user_id == user_id))
    cart = result.scalars().first()
    if not cart:
        cart = CartModel(user_id=user_id)
        db.add(cart)
        await db.flush()
    return cart


@router.post(
    "/items/",
    response_model=MessageResponseSchema,
    summary="Add a movie to the cart",
    status_code=status.HTTP_200_OK,
    responses={
        404: {
            "description": "Movie not found.",
            "content": {"application/json": {"example": {"detail": "Movie not found."}}},
        },
        409: {
            "description": "Movie already in cart or already purchased.",
            "content": {"application/json": {"example": {"detail": "Movie already in cart."}}},
        },
    }
)
async def add_to_cart(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    if await is_movie_purchased(db, user_id, movie_id):
        raise HTTPException(status_code=409, detail="Movie already purchased. Repeat purchases are not allowed.")

    cart = await get_or_create_cart(db, user_id)

    existing_item = await db.execute(
        select(CartItemModel).where(
            CartItemModel.cart_id == cart.id,
            CartItemModel.movie_id == movie_id,
        )
    )
    if existing_item.scalars().first():
        raise HTTPException(status_code=409, detail="Movie already in cart.")

    cart_item = CartItemModel(cart_id=cart.id, movie_id=movie_id)
    db.add(cart_item)
    await db.commit()

    return MessageResponseSchema(message="Movie added to cart.")


@router.delete(
    "/items/{movie_id}/",
    response_model=MessageResponseSchema,
    summary="Remove a movie from the cart",
    responses={
        404: {
            "description": "Movie not found in cart.",
            "content": {"application/json": {"example": {"detail": "Movie not found in cart."}}},
        },
    }
)
async def remove_from_cart(
        movie_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    cart = await get_or_create_cart(db, user_id)

    result = await db.execute(
        select(CartItemModel).where(
            CartItemModel.cart_id == cart.id,
            CartItemModel.movie_id == movie_id,
        )
    )
    cart_item = result.scalars().first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Movie not found in cart.")

    await db.delete(cart_item)
    await db.commit()

    return MessageResponseSchema(message="Movie removed from cart.")


@router.get(
    "/",
    response_model=CartResponseSchema,
    summary="Get the current user's cart",
)
async def get_cart(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> CartResponseSchema:
    cart = await get_or_create_cart(db, user_id)
    await db.commit()

    result = await db.execute(
        select(CartItemModel)
        .where(CartItemModel.cart_id == cart.id)
        .options(
            joinedload(CartItemModel.movie).joinedload(MovieModel.genres)
        )
    )
    cart_items = result.unique().scalars().all()

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


@router.delete(
    "/",
    response_model=MessageResponseSchema,
    summary="Clear the entire cart",
)
async def clear_cart(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    cart = await get_or_create_cart(db, user_id)

    await db.execute(
        CartItemModel.__table__.delete().where(CartItemModel.cart_id == cart.id)
    )
    await db.commit()

    return MessageResponseSchema(message="Cart cleared successfully.")


@router.get(
    "/users/{user_id}/",
    response_model=CartResponseSchema,
    summary="Admin/Moderator: view a specific user's cart",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
        404: {
            "description": "Cart not found.",
            "content": {"application/json": {"example": {"detail": "Cart not found."}}},
        },
    }
)
async def get_user_cart(
        user_id: int,
        db: AsyncSession = Depends(get_db),
        current_user_id: int = Depends(get_current_user_id),
) -> CartResponseSchema:
    result = await db.execute(
        select(UserModel).options(joinedload(UserModel.group)).filter_by(id=current_user_id)
    )
    current_user = result.scalars().first()
    if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(status_code=403, detail="No permission.")

    cart_result = await db.execute(select(CartModel).where(CartModel.user_id == user_id))
    cart = cart_result.scalars().first()
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found.")

    items_result = await db.execute(
        select(CartItemModel)
        .where(CartItemModel.cart_id == cart.id)
        .options(joinedload(CartItemModel.movie).joinedload(MovieModel.genres))
    )
    cart_items = items_result.unique().scalars().all()

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

