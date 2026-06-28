from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    MovieModel,
    GenreModel,
    StarModel,
    DirectorModel,
    CertificationModel,
)
from database.models.orders import OrderModel, OrderItemModel, OrderStatusEnum
from database.models.payments import PaymentModel, PaymentStatusEnum


async def create_regular_user(db_session: AsyncSession, email: str = "paymentuser@example.com") -> UserModel:
    """Helper to create an active regular user."""
    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
    result = await db_session.execute(stmt)
    group = result.scalars().first()

    user = UserModel.create(
        email=email,
        raw_password="UserPass123!",
        group_id=group.id
    )
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_moderator(db_session: AsyncSession) -> UserModel:
    """Helper to create an active moderator user."""
    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.MODERATOR)
    result = await db_session.execute(stmt)
    group = result.scalars().first()

    user = UserModel.create(
        email="paymentmoderator@example.com",
        raw_password="ModeratorPass123!",
        group_id=group.id
    )
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_test_movie(db_session: AsyncSession, name: str = "Payment Test Movie") -> MovieModel:
    """Helper to create a movie with genre, star, director, certification."""
    certification = CertificationModel(name=f"PG-13-{name}")
    genre = GenreModel(name=f"Action-{name}")
    star = StarModel(name=f"Star-{name}")
    director = DirectorModel(name=f"Director-{name}")
    db_session.add_all([certification, genre, star, director])
    await db_session.flush()

    movie = MovieModel(
        name=name,
        year=2020,
        imdb=7.5,
        price=9.99,
        time=120,
        votes=1000,
        meta_score=70,
        gross=1000000,
        description="A test movie for payments.",
        certification_id=certification.id,
        genres=[genre],
        stars=[star],
        directors=[director],
    )
    db_session.add(movie)
    await db_session.commit()
    await db_session.refresh(movie)
    return movie


async def create_test_order(db_session: AsyncSession, user: UserModel, movie: MovieModel) -> OrderModel:
    """Helper to create a pending order with one item."""
    order = OrderModel(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=movie.price,
    )
    db_session.add(order)
    await db_session.flush()

    order_item = OrderItemModel(
        order_id=order.id,
        movie_id=movie.id,
        price_at_order=movie.price,
    )
    db_session.add(order_item)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_create_checkout_session_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successful creation of a Stripe checkout session."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    order = await create_test_order(db_session, user, movie)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-session"

    with patch("routes.payments.stripe.checkout.Session.create", return_value=mock_session):
        response = await client.post(
            f"/api/v1/payments/orders/{order.id}/checkout/",
            headers={"Authorization": f"Bearer {access_token}"}
        )

    assert response.status_code == 200
    assert response.json()["checkout_url"] == "https://checkout.stripe.com/test-session"


@pytest.mark.asyncio
async def test_create_checkout_session_order_not_found(client, db_session, jwt_manager, seed_user_groups):
    """Test checkout session creation with nonexistent order."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        "/api/v1/payments/orders/9999/checkout/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found."


@pytest.mark.asyncio
async def test_create_checkout_session_already_paid_order(client, db_session, jwt_manager, seed_user_groups):
    """Test that checkout fails for a non-pending order."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    order = await create_test_order(db_session, user, movie)
    order.status = OrderStatusEnum.PAID
    await db_session.commit()

    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/payments/orders/{order.id}/checkout/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Order is not pending."


@pytest.mark.asyncio
async def test_create_checkout_session_price_changed_warning(client, db_session, jwt_manager, seed_user_groups):
    """Test that a price change triggers a warning in the checkout response."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    order = await create_test_order(db_session, user, movie)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    movie.price = 19.99
    await db_session.commit()

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-session"

    with patch("routes.payments.stripe.checkout.Session.create", return_value=mock_session):
        response = await client.post(
            f"/api/v1/payments/orders/{order.id}/checkout/",
            headers={"Authorization": f"Bearer {access_token}"}
        )

    assert response.status_code == 200
    assert response.json()["price_changed_warning"] is not None
    assert "9.99" in response.json()["price_changed_warning"]


@pytest.mark.asyncio
async def test_get_payments_history_empty(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving an empty payment history."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.get(
        "/api/v1/payments/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_payments_history_with_data(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving payment history with existing payments."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    order = await create_test_order(db_session, user, movie)

    payment = PaymentModel(
        user_id=user.id,
        order_id=order.id,
        amount=movie.price,
        status=PaymentStatusEnum.SUCCESSFUL,
        external_payment_id="pi_test_123",
    )
    db_session.add(payment)
    await db_session.commit()

    access_token = jwt_manager.create_access_token({"user_id": user.id})
    response = await client.get(
        "/api/v1/payments/",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "successful"
    assert data[0]["external_payment_id"] == "pi_test_123"


@pytest.mark.asyncio
async def test_moderator_can_view_all_payments(client, db_session, jwt_manager, seed_user_groups):
    """Test that a moderator can view all payments with filters."""
    user = await create_regular_user(db_session)
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)
    order = await create_test_order(db_session, user, movie)

    payment = PaymentModel(
        user_id=user.id,
        order_id=order.id,
        amount=movie.price,
        status=PaymentStatusEnum.SUCCESSFUL,
        external_payment_id="pi_test_456",
    )
    db_session.add(payment)
    await db_session.commit()

    moderator_token = jwt_manager.create_access_token({"user_id": moderator.id})
    response = await client.get(
        "/api/v1/payments/all/",
        headers={"Authorization": f"Bearer {moderator_token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_moderator_can_filter_payments_by_status(client, db_session, jwt_manager, seed_user_groups):
    """Test filtering all-payments by status."""
    user = await create_regular_user(db_session)
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)
    order = await create_test_order(db_session, user, movie)

    payment = PaymentModel(
        user_id=user.id,
        order_id=order.id,
        amount=movie.price,
        status=PaymentStatusEnum.REFUNDED,
        external_payment_id="pi_test_789",
    )
    db_session.add(payment)
    await db_session.commit()

    moderator_token = jwt_manager.create_access_token({"user_id": moderator.id})

    response = await client.get(
        "/api/v1/payments/all/?status_filter=refunded",
        headers={"Authorization": f"Bearer {moderator_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    response_no_match = await client.get(
        "/api/v1/payments/all/?status_filter=successful",
        headers={"Authorization": f"Bearer {moderator_token}"}
    )
    assert response_no_match.status_code == 200
    assert len(response_no_match.json()) == 0


@pytest.mark.asyncio
async def test_regular_user_cannot_view_all_payments(client, db_session, jwt_manager, seed_user_groups):
    """Test that a regular user cannot access the all-payments endpoint."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.get(
        "/api/v1/payments/all/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_success_page_returns_html(client):
    """Test the payment success confirmation page."""
    response = await client.get("/api/v1/payments/success/")
    assert response.status_code == 200
    assert "Payment Successful" in response.text


@pytest.mark.asyncio
async def test_cancel_page_returns_html(client):
    """Test the payment cancel confirmation page."""
    response = await client.get("/api/v1/payments/cancel/")
    assert response.status_code == 200
    assert "Payment Canceled" in response.text
