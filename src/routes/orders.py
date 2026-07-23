from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from config.dependencies import get_current_user_id, get_order_service
from database.models.orders import OrderStatusEnum
from schemas import OrderResponseSchema, MessageResponseSchema
from services.orders import OrderService

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
    user_id: int = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponseSchema:
    return await service.create_order(user_id)


@router.get(
    "/",
    response_model=List[OrderResponseSchema],
    summary="Get list of current user's orders",
)
async def get_orders(
    user_id: int = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> List[OrderResponseSchema]:
    return await service.get_orders(user_id)


@router.get(
    "/all/",
    response_model=List[OrderResponseSchema],
    summary="Moderator: get all orders with filters",
    responses={
        403: {
            "description": "No permission.",
            "content": {"application/json": {"example": {"detail": "No permission."}}},
        },
    }
)
async def get_all_orders(
    user_id_filter: Optional[int] = Query(None),
    status_filter: Optional[OrderStatusEnum] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user_id: int = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> List[OrderResponseSchema]:
    return await service.get_all_orders(current_user_id, user_id_filter, status_filter, date_from, date_to)


@router.get(
    "/{order_id}/",
    response_model=OrderResponseSchema,
    summary="Get an order by id",
    responses={
        404: {
            "description": "Order not found.",
            "content": {"application/json": {"example": {"detail": "Order not found."}}},
        }
    }
)
async def get_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> OrderResponseSchema:
    return await service.get_order(order_id, user_id)


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
    user_id: int = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> MessageResponseSchema:
    return await service.cancel_order(order_id, user_id)


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
    user_id: int = Depends(get_current_user_id),
    service: OrderService = Depends(get_order_service),
) -> MessageResponseSchema:
    return await service.pay_order(order_id, user_id)
