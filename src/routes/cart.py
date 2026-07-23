from fastapi import APIRouter, Depends, status

from config.dependencies import get_current_user_id, get_cart_service
from schemas import CartResponseSchema, MessageResponseSchema
from services.cart import CartService

router = APIRouter()


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
    user_id: int = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> MessageResponseSchema:
    return await service.add_item(user_id, movie_id)


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
    user_id: int = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> MessageResponseSchema:
    return await service.remove_item(user_id, movie_id)


@router.get(
    "/",
    response_model=CartResponseSchema,
    summary="Get the current user's cart",
)
async def get_cart(
    user_id: int = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CartResponseSchema:
    return await service.get_cart(user_id)


@router.delete(
    "/",
    response_model=MessageResponseSchema,
    summary="Clear the entire cart",
)
async def clear_cart(
    user_id: int = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> MessageResponseSchema:
    return await service.clear_cart(user_id)


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
    current_user_id: int = Depends(get_current_user_id),
    service: CartService = Depends(get_cart_service),
) -> CartResponseSchema:
    return await service.get_user_cart_by_moderator(user_id, current_user_id)
