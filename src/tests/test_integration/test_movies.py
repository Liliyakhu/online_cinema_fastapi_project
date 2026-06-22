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


@pytest.fixture
def auth_headers(jwt_manager):
    """Helper to build Authorization header for a given user_id."""
    def _make(user_id: int) -> dict:
        token = jwt_manager.create_access_token({"user_id": user_id})
        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest.mark.asyncio
async def create_moderator(db_session: AsyncSession) -> UserModel:
    """Helper to create an active moderator user."""
    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.MODERATOR)
    result = await db_session.execute(stmt)
    group = result.scalars().first()

    user = UserModel.create(
        email="moderator@example.com",
        raw_password="ModeratorPass123!",
        group_id=group.id
    )
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def create_regular_user(db_session: AsyncSession, email: str = "user@example.com") -> UserModel:
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


@pytest.mark.asyncio
async def create_test_movie(db_session: AsyncSession) -> MovieModel:
    """Helper to create a movie with genre, star, director, certification."""
    certification = CertificationModel(name="PG-13")
    genre = GenreModel(name="Action")
    star = StarModel(name="Test Star")
    director = DirectorModel(name="Test Director")
    db_session.add_all([certification, genre, star, director])
    await db_session.flush()

    movie = MovieModel(
        name="Test Movie",
        year=2020,
        imdb=7.5,
        price=9.99,
        time=120,
        votes=1000,
        meta_score=70,
        gross=1000000,
        description="A test movie description.",
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
async def test_get_movie_list_success(client, db_session, seed_user_groups):
    """Test successful retrieval of paginated movie list."""
    await create_test_movie(db_session)

    response = await client.get("/api/v1/cinema/movies/?page=1&per_page=10")
    assert response.status_code == 200, "Expected status code 200."

    data = response.json()
    assert data["total"] == 1, "Expected one movie in the list."
    assert data["items"][0]["name"] == "Test Movie", "Movie name does not match."
    assert data["page"] == 1
    assert data["per_page"] == 10


@pytest.mark.asyncio
async def test_get_movie_list_empty(client, seed_user_groups):
    """Test movie list when no movies exist."""
    response = await client.get("/api/v1/cinema/movies/?page=1&per_page=10")
    assert response.status_code == 404, "Expected status code 404 for empty movie list."
    assert response.json()["detail"] == "No movies found."


@pytest.mark.asyncio
async def test_get_movie_list_search(client, db_session, seed_user_groups):
    """Test movie list search functionality."""
    await create_test_movie(db_session)

    response = await client.get("/api/v1/cinema/movies/?search=Test")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1

    response_no_match = await client.get("/api/v1/cinema/movies/?search=Nonexistent")
    assert response_no_match.status_code == 404


@pytest.mark.asyncio
async def test_get_movie_list_filter_by_year(client, db_session, seed_user_groups):
    """Test movie list filtering by year."""
    await create_test_movie(db_session)

    response = await client.get("/api/v1/cinema/movies/?year=2020")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response_no_match = await client.get("/api/v1/cinema/movies/?year=1999")
    assert response_no_match.status_code == 404


@pytest.mark.asyncio
async def test_get_movie_list_filter_by_genre(client, db_session, seed_user_groups):
    """Test movie list filtering by genre ID."""
    movie = await create_test_movie(db_session)

    genre_result = await db_session.execute(
        select(GenreModel).where(GenreModel.name == "Action")
    )
    genre = genre_result.scalars().first()
    genre_id = genre.id

    response = await client.get(f"/api/v1/cinema/movies/?genre_id={genre_id}")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response_no_match = await client.get("/api/v1/cinema/movies/?genre_id=9999")
    assert response_no_match.status_code == 404

@pytest.mark.asyncio
async def test_get_movie_list_sort_by_price(client, db_session, seed_user_groups):
    """Test movie list sorting by price."""
    certification = CertificationModel(name="PG-13")
    db_session.add(certification)
    await db_session.flush()

    cheap_movie = MovieModel(
        name="Cheap Movie", year=2020, imdb=6.0, price=4.99, time=90,
        votes=100, description="Cheap movie.", certification_id=certification.id,
    )
    expensive_movie = MovieModel(
        name="Expensive Movie", year=2021, imdb=8.0, price=19.99, time=150,
        votes=500, description="Expensive movie.", certification_id=certification.id,
    )
    db_session.add_all([cheap_movie, expensive_movie])
    await db_session.commit()

    response = await client.get("/api/v1/cinema/movies/?sort_by=price&sort_order=asc")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["name"] == "Cheap Movie"
    assert items[1]["name"] == "Expensive Movie"

    response_desc = await client.get("/api/v1/cinema/movies/?sort_by=price&sort_order=desc")
    items_desc = response_desc.json()["items"]
    assert items_desc[0]["name"] == "Expensive Movie"
    assert items_desc[1]["name"] == "Cheap Movie"


@pytest.mark.asyncio
async def test_create_movie_success(client, db_session, jwt_manager, seed_user_groups):
    """Test successful movie creation by a moderator."""
    moderator = await create_moderator(db_session)

    certification = CertificationModel(name="R")
    genre = GenreModel(name="Drama")
    star = StarModel(name="New Star")
    director = DirectorModel(name="New Director")
    db_session.add_all([certification, genre, star, director])
    await db_session.commit()
    await db_session.refresh(certification)
    await db_session.refresh(genre)
    await db_session.refresh(star)
    await db_session.refresh(director)

    access_token = jwt_manager.create_access_token({"user_id": moderator.id})

    payload = {
        "name": "New Movie",
        "year": 2022,
        "imdb": 7.0,
        "price": 9.99,
        "time": 110,
        "votes": 5000,
        "meta_score": 65,
        "gross": 5000000,
        "description": "A brand new movie.",
        "certification_id": certification.id,
        "genre_ids": [genre.id],
        "star_ids": [star.id],
        "director_ids": [director.id],
    }

    response = await client.post(
        "/api/v1/cinema/movies/",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201, "Expected status code 201 for movie creation."
    data = response.json()
    assert data["name"] == "New Movie"
    assert data["certification"]["name"] == "R"
    assert len(data["genres"]) == 1


@pytest.mark.asyncio
async def test_create_movie_forbidden_for_regular_user(client, db_session, jwt_manager, seed_user_groups):
    """Test that regular users cannot create movies."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    payload = {
        "name": "Unauthorized Movie",
        "year": 2022,
        "imdb": 7.0,
        "price": 9.99,
        "time": 110,
        "votes": 5000,
        "description": "Should not be created.",
        "certification_id": 1,
        "genre_ids": [],
        "star_ids": [],
        "director_ids": [],
    }

    response = await client.post(
        "/api/v1/cinema/movies/",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403, "Expected status code 403 for non-moderator user."
    assert response.json()["detail"] == "No permission."


@pytest.mark.asyncio
async def test_add_to_favorites_success(client, db_session, jwt_manager, seed_user_groups):
    """Test adding a movie to favorites."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/favorites/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Movie added to favorites."


@pytest.mark.asyncio
async def test_add_to_favorites_already_exists(client, db_session, jwt_manager, seed_user_groups):
    """Test adding the same movie to favorites twice returns conflict."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cinema/movies/{movie.id}/favorites/", headers=headers)
    response = await client.post(f"/api/v1/cinema/movies/{movie.id}/favorites/", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Movie already in favorites."


@pytest.mark.asyncio
async def test_remove_from_favorites_success(client, db_session, jwt_manager, seed_user_groups):
    """Test removing a movie from favorites."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cinema/movies/{movie.id}/favorites/", headers=headers)
    response = await client.delete(f"/api/v1/cinema/movies/{movie.id}/favorites/", headers=headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Movie deleted from favorites."


@pytest.mark.asyncio
async def test_get_favorites_list(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving favorites list."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(f"/api/v1/cinema/movies/{movie.id}/favorites/", headers=headers)
    response = await client.get("/api/v1/cinema/movies/favorites/", headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.asyncio
async def test_like_movie_toggle(client, db_session, jwt_manager, seed_user_groups):
    """Test liking, then unliking a movie via toggle."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/like/",
        json={"is_like": True},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["likes_count"] == 1
    assert response.json()["user_like"] is True

    response_toggle = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/like/",
        json={"is_like": True},
        headers=headers
    )
    assert response_toggle.json()["likes_count"] == 0
    assert response_toggle.json()["user_like"] is None


@pytest.mark.asyncio
async def test_rate_movie_success(client, db_session, jwt_manager, seed_user_groups):
    """Test rating a movie."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/rate/",
        json={"rating": 8},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["average_rating"] == 8.0
    assert response.json()["user_rating"] == 8


@pytest.mark.asyncio
async def test_rate_movie_invalid_rating(client, db_session, jwt_manager, seed_user_groups):
    """Test rating a movie with invalid value returns 422."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/rate/",
        json={"rating": 15},
        headers=headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_comment_success(client, db_session, jwt_manager, seed_user_groups):
    """Test creating a root comment on a movie."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "Great movie!"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 201
    assert response.json()["text"] == "Great movie!"
    assert response.json()["replies"] == []


@pytest.mark.asyncio
async def test_create_reply_success(client, db_session, jwt_manager, seed_user_groups):
    """Test creating a reply to a comment."""
    user1 = await create_regular_user(db_session, email="user1@example.com")
    user2 = await create_regular_user(db_session, email="user2@example.com")
    movie = await create_test_movie(db_session)
    token1 = jwt_manager.create_access_token({"user_id": user1.id})
    token2 = jwt_manager.create_access_token({"user_id": user2.id})

    comment_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "Original comment"},
        headers={"Authorization": f"Bearer {token1}"}
    )
    comment_id = comment_response.json()["id"]

    reply_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "A reply", "parent_id": comment_id},
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert reply_response.status_code == 201
    assert reply_response.json()["text"] == "A reply"


@pytest.mark.asyncio
async def test_reply_to_reply_forbidden(client, db_session, jwt_manager, seed_user_groups):
    """Test that replying to a reply is forbidden (one level depth only)."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    comment_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "Root comment"},
        headers=headers
    )
    comment_id = comment_response.json()["id"]

    reply_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "First reply", "parent_id": comment_id},
        headers=headers
    )
    reply_id = reply_response.json()["id"]

    nested_reply_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "Reply to reply", "parent_id": reply_id},
        headers=headers
    )
    assert nested_reply_response.status_code == 400
    assert nested_reply_response.json()["detail"] == "Cannot reply to a reply."


@pytest.mark.asyncio
async def test_get_comments_list(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving comments with nested replies."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    comment_response = await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "Root comment"},
        headers=headers
    )
    comment_id = comment_response.json()["id"]

    await client.post(
        f"/api/v1/cinema/movies/{movie.id}/comments/",
        json={"text": "A reply", "parent_id": comment_id},
        headers=headers
    )

    response = await client.get(f"/api/v1/cinema/movies/{movie.id}/comments/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert len(data[0]["replies"]) == 1


@pytest.mark.asyncio
async def test_update_movie_success(client, db_session, jwt_manager, seed_user_groups):
    """Test moderator successfully updates a movie."""
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": moderator.id})

    response = await client.patch(
        f"/api/v1/cinema/movies/{movie.id}/",
        json={"year": 2023},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["year"] == 2023


@pytest.mark.asyncio
async def test_update_movie_forbidden_for_regular_user(client, db_session, jwt_manager, seed_user_groups):
    """Test that regular users cannot update movies."""
    user = await create_regular_user(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.patch(
        f"/api/v1/cinema/movies/{movie.id}/",
        json={"year": 2023},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_movie_success(client, db_session, jwt_manager, seed_user_groups):
    """Test moderator successfully deletes a movie."""
    moderator = await create_moderator(db_session)
    movie = await create_test_movie(db_session)
    access_token = jwt_manager.create_access_token({"user_id": moderator.id})

    response = await client.delete(
        f"/api/v1/cinema/movies/{movie.id}/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204

