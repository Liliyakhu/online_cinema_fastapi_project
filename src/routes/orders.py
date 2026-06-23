from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import get_db, UserModel, UserGroupEnum
from database.models import CartModel, CartItemModel, MovieModel
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from schemas import OrderResponseSchema, MessageResponseSchema
from schemas.orders import OrderItemSchema
from config.dependencies import get_current_user_id
from routes.cart import is_movie_purchased, get_or_create_cart

router = APIRouter()


@router.post(
    "/",
    response_model=OrderResponseSchema,
    summary="Create an order from the cart (checkout)",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "description": "Cart is empty.",
            "content": {"application/json": {"example": {"detail": "Cart is empty."}}},
        },
    }
)
async def create_order(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> OrderResponseSchema:
    cart = await get_or_create_cart(db, user_id)

    result = await db.execute(
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

        if await is_movie_purchased(db, user_id, movie.id):
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
    db.add(order)
    await db.flush()

    for cart_item in valid_items:
        order_item = OrderItemModel(
            order_id=order.id,
            movie_id=cart_item.movie.id,
            price_at_order=cart_item.movie.price,
        )
        db.add(order_item)
        await db.delete(cart_item)

    await db.commit()

    result = await db.execute(
        select(OrderModel)
        .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
        .filter_by(id=order.id)
    )
    order = result.unique().scalar_one()

    items_schema = [
        OrderItemSchema(
            movie_id=item.movie_id,
            title=item.movie.name,
            price_at_order=item.price_at_order,
        )
        for item in order.items
    ]

    return OrderResponseSchema(
        id=order.id,
        created_at=order.created_at,
        status=order.status,
        total_amount=order.total_amount,
        items=items_schema,
    )


@router.get(
    "/",
    response_model=List[OrderResponseSchema],
    summary="Get list of current user's orders",
)
async def get_orders(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> List[OrderResponseSchema]:
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.user_id == user_id)
        .options(joinedload(OrderModel.items).joinedload(OrderItemModel.movie))
        .order_by(OrderModel.created_at.desc())
    )
    orders = result.unique().scalars().all()

    return [
        OrderResponseSchema(
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
        for order in orders
    ]


@router.post(
    "/{order_id}/cancel/",
    response_model=MessageResponseSchema,
    summary="Cancel a pending order",
    responses={
        404: {
            "description": "Order not found.",
            "content": {"application/json": {"example": {"detail": "Order not found."}}},
        },
        409: {
            "description": "Only pending orders can be canceled.",
            "content": {"application/json": {"example": {"detail": "Only pending orders can be canceled."}}},
        },
    }
)
async def cancel_order(
        order_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    order = await db.get(OrderModel, order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(status_code=409, detail="Only pending orders can be canceled.")

    order.status = OrderStatusEnum.CANCELED
    await db.commit()

    return MessageResponseSchema(message="Order canceled successfully.")


@router.post(
    "/{order_id}/pay/",
    response_model=MessageResponseSchema,
    summary="Pay for a pending order (simplified, no real payment gateway)",
    responses={
        404: {
            "description": "Order not found.",
            "content": {"application/json": {"example": {"detail": "Order not found."}}},
        },
        409: {
            "description": "Only pending orders can be paid.",
            "content": {"application/json": {"example": {"detail": "Only pending orders can be paid."}}},
        },
    }
)
async def pay_order(
        order_id: int,
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id),
) -> MessageResponseSchema:
    order = await db.get(OrderModel, order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(status_code=409, detail="Only pending orders can be paid.")

    order.status = OrderStatusEnum.PAID
    await db.commit()

    # TODO: Send email confirmation once email integration is wired up for orders

    return MessageResponseSchema(message="Order paid successfully.")
