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


async def create_regular_user(db_session: AsyncSession, email: str = "orderuser@example.com") -> UserModel:
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
        email="ordermoderator@example.com",
        raw_password="ModeratorPass123!",
        group_id=group.id
    )
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_test_movie(db_session: AsyncSession, name: str = "Order Test Movie") -> MovieModel:
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
        description="A test movie for orders.",
        certification_id=certification.id,
        genres=[genre],
        stars=[star],
        directors=[director],
    )
    db_session.add(movie)
    await db_session.commit()
    await db_session.refresh(movie)
    return movie


@pytest.mark.asyncio
async def test_create_order_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successful order creation from cart."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    response = await client.post("/api/v1/orders/", headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert len(data["items"]) == 1
    assert float(data["total_amount"]) == 9.99


@pytest.mark.asyncio
async def test_create_order_empty_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test creating an order with an empty cart returns 400."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        "/api/v1/orders/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Cart is empty."


@pytest.mark.asyncio
async def test_order_clears_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test that creating an order removes items from the cart."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    await client.post("/api/v1/orders/", headers=headers)

    cart_response = await client.get("/api/v1/cart/", headers=headers)
    assert cart_response.json()["total_items"] == 0


@pytest.mark.asyncio
async def test_get_orders_list(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving the list of orders for the current user."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    await client.post("/api/v1/orders/", headers=headers)

    response = await client.get("/api/v1/orders/", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_pay_order_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successfully paying for a pending order."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    order_response = await client.post("/api/v1/orders/", headers=headers)
    order_id = order_response.json()["id"]

    response = await client.post(f"/api/v1/orders/{order_id}/pay/", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Order paid successfully."


@pytest.mark.asyncio
async def test_pay_order_twice_fails(client, db_session, jwt_manager, seed_user_groups):
    """Test that paying for an already-paid order returns conflict."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    order_response = await client.post("/api/v1/orders/", headers=headers)
    order_id = order_response.json()["id"]

    await client.post(f"/api/v1/orders/{order_id}/pay/", headers=headers)
    response = await client.post(f"/api/v1/orders/{order_id}/pay/", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only pending orders can be paid."


@pytest.mark.asyncio
async def test_cancel_pending_order_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successfully canceling a pending order."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    order_response = await client.post("/api/v1/orders/", headers=headers)
    order_id = order_response.json()["id"]

    response = await client.post(f"/api/v1/orders/{order_id}/cancel/", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Order canceled successfully."


@pytest.mark.asyncio
async def test_cancel_paid_order_fails(client, db_session, jwt_manager, seed_user_groups):
    """Test that canceling an already-paid order returns conflict."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    order_response = await client.post("/api/v1/orders/", headers=headers)
    order_id = order_response.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/pay/", headers=headers)

    response = await client.post(f"/api/v1/orders/{order_id}/cancel/", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Only pending orders can be canceled."


@pytest.mark.asyncio
async def test_get_order_details(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving order details by ID."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    order_response = await client.post("/api/v1/orders/", headers=headers)
    order_id = order_response.json()["id"]

    response = await client.get(f"/api/v1/orders/{order_id}/", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == order_id


@pytest.mark.asyncio
async def test_cannot_repurchase_paid_movie(client, db_session, jwt_manager, seed_user_groups):
    """Test that a movie already purchased cannot be added to cart again."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    order_response = await client.post("/api/v1/orders/", headers=headers)
    order_id = order_response.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/pay/", headers=headers)

    response = await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Movie already purchased. Repeat purchases are not allowed."


@pytest.mark.asyncio
async def test_moderator_can_view_all_orders(client, db_session, jwt_manager, seed_user_groups):
    """Test that a moderator can view all orders with filters."""
    user = await create_regular_user(db_session)
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)

    user_token = jwt_manager.create_access_token({"user_id": user.id})
    await client.post(
        f"/api/v1/cart/items/?movie_id={movie.id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    await client.post("/api/v1/orders/", headers={"Authorization": f"Bearer {user_token}"})

    moderator_token = jwt_manager.create_access_token({"user_id": moderator.id})
    response = await client.get(
        "/api/v1/orders/all/",
        headers={"Authorization": f"Bearer {moderator_token}"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_regular_user_cannot_view_all_orders(client, db_session, jwt_manager, seed_user_groups):
    """Test that a regular user cannot access the all-orders endpoint."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.get(
        "/api/v1/orders/all/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403
