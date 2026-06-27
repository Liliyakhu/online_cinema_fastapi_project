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
from database.models import CartModel, CartItemModel


async def create_regular_user(db_session: AsyncSession, email: str = "cartuser@example.com") -> UserModel:
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
        email="cartmoderator@example.com",
        raw_password="ModeratorPass123!",
        group_id=group.id
    )
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_test_movie(db_session: AsyncSession, name: str = "Cart Test Movie") -> MovieModel:
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
        description="A test movie for cart.",
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
async def test_add_to_cart_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successfully adding a movie to the cart."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/cart/items/?movie_id={movie.id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Movie added to cart."


@pytest.mark.asyncio
async def test_add_duplicate_movie_to_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test that adding the same movie twice returns a conflict."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    response = await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Movie already in cart."


@pytest.mark.asyncio
async def test_add_nonexistent_movie_to_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test adding a nonexistent movie returns 404."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        "/api/v1/cart/items/?movie_id=9999",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie not found."


@pytest.mark.asyncio
async def test_remove_from_cart_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successfully removing a movie from the cart."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    response = await client.delete(f"/api/v1/cart/items/{movie.id}/", headers=headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Movie removed from cart."


@pytest.mark.asyncio
async def test_remove_nonexistent_item_from_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test removing a movie not in the cart returns 404."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.delete(
        f"/api/v1/cart/items/{movie.id}/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie not found in cart."


@pytest.mark.asyncio
async def test_get_cart_with_items(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving cart contents with movie details."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    response = await client.get("/api/v1/cart/", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_items"] == 1
    assert data["items"][0]["title"] == "Cart Test Movie"
    assert data["items"][0]["year"] == 2020
    assert "genres" in data["items"][0]


@pytest.mark.asyncio
async def test_get_empty_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving an empty cart."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.get(
        "/api/v1/cart/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["total_items"] == 0
    assert response.json()["total_price"] == 0


@pytest.mark.asyncio
async def test_clear_cart_success(client, db_session, jwt_manager, seed_user_groups):
    """Test clearing all items from the cart."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cart/items/?movie_id={movie.id}", headers=headers)
    response = await client.delete("/api/v1/cart/", headers=headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Cart cleared successfully."

    cart_response = await client.get("/api/v1/cart/", headers=headers)
    assert cart_response.json()["total_items"] == 0


@pytest.mark.asyncio
async def test_admin_can_view_user_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test that a moderator can view another user's cart."""
    user = await create_regular_user(db_session)
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)

    user_token = jwt_manager.create_access_token({"user_id": user.id})
    await client.post(
        f"/api/v1/cart/items/?movie_id={movie.id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    moderator_token = jwt_manager.create_access_token({"user_id": moderator.id})
    response = await client.get(
        f"/api/v1/cart/users/{user.id}/",
        headers={"Authorization": f"Bearer {moderator_token}"}
    )
    assert response.status_code == 200
    assert response.json()["total_items"] == 1


@pytest.mark.asyncio
async def test_regular_user_cannot_view_other_user_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test that a regular user cannot view another user's cart."""
    user1 = await create_regular_user(db_session, email="user1cart@example.com")
    user2 = await create_regular_user(db_session, email="user2cart@example.com")

    token1 = jwt_manager.create_access_token({"user_id": user1.id})
    response = await client.get(
        f"/api/v1/cart/users/{user2.id}/",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_movie_blocked_by_cart(client, db_session, jwt_manager, seed_user_groups):
    """Test that a moderator cannot delete a movie that exists in a user's cart."""
    user = await create_regular_user(db_session)
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)

    user_token = jwt_manager.create_access_token({"user_id": user.id})
    await client.post(
        f"/api/v1/cart/items/?movie_id={movie.id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )

    moderator_token = jwt_manager.create_access_token({"user_id": moderator.id})
    response = await client.delete(
        f"/api/v1/cinema/movies/{movie.id}/",
        headers={"Authorization": f"Bearer {moderator_token}"}
    )
    assert response.status_code == 409

