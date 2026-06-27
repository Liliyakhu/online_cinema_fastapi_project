from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

from database import UserModel, UserGroupModel, UserGroupEnum, UserProfileModel


async def create_regular_user(db_session, email: str = "profileuser@example.com") -> UserModel:
    """Helper to create an active regular user."""
    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
    result = await db_session.execute(stmt)
    group = result.scalars().first()

    user = UserModel.create(email=email, raw_password="UserPass123!", group_id=group.id)
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_moderator(db_session) -> UserModel:
    """Helper to create an active moderator user."""
    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.MODERATOR)
    result = await db_session.execute(stmt)
    group = result.scalars().first()

    user = UserModel.create(email="profilemoderator@example.com", raw_password="ModeratorPass123!", group_id=group.id)
    user.is_active = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def fake_jpeg() -> BytesIO:
    """Helper to create a real, valid in-memory JPEG image for tests."""
    img = Image.new("RGB", (50, 50), color="blue")
    img_bytes = BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)
    return img_bytes


@pytest.mark.asyncio
async def test_create_profile_success(client, db_session, jwt_manager, seed_user_groups, s3_storage_fake):
    """Test successful profile creation with avatar upload."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "first_name": "Olena",
            "last_name": "Ivanenko",
            "gender": "woman",
            "date_of_birth": "1990-05-15",
            "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "olena"
    assert data["last_name"] == "ivanenko"
    assert data["gender"] == "woman"
    assert data["info"] == "Test bio"
    assert "avatar" in data

    avatar_key = f"avatars/{user.id}_avatar.jpg"
    assert avatar_key in s3_storage_fake.storage


@pytest.mark.asyncio
async def test_create_profile_already_exists(client, db_session, jwt_manager, seed_user_groups):
    """Test that creating a second profile for the same user fails."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "first_name": "Olena",
        "last_name": "Ivanenko",
        "gender": "woman",
        "date_of_birth": "1990-05-15",
        "info": "Test bio",
    }

    await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers, data=payload,
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )
    response = await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers, data=payload,
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "User already has a profile."


@pytest.mark.asyncio
async def test_create_profile_forbidden_for_other_user(client, db_session, jwt_manager, seed_user_groups):
    """Test that a regular user cannot create a profile for another user."""
    user1 = await create_regular_user(db_session, email="user1profile@example.com")
    user2 = await create_regular_user(db_session, email="user2profile@example.com")
    access_token = jwt_manager.create_access_token({"user_id": user1.id})

    response = await client.post(
        f"/api/v1/accounts/users/{user2.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_moderator_can_create_profile_for_other_user(client, db_session, jwt_manager, seed_user_groups):
    """Test that a moderator can create a profile for another user."""
    user = await create_regular_user(db_session)
    moderator = await create_moderator(db_session)
    access_token = jwt_manager.create_access_token({"user_id": moderator.id})

    response = await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_profile_invalid_name(client, db_session, jwt_manager, seed_user_groups):
    """Test that profile creation fails with non-English characters in name."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "first_name": "Олена", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_profile_invalid_gender(client, db_session, jwt_manager, seed_user_groups):
    """Test that profile creation fails with invalid gender."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "other",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 422
    assert "Gender must be one of" in str(response.json())


@pytest.mark.asyncio
async def test_create_profile_underage(client, db_session, jwt_manager, seed_user_groups):
    """Test that profile creation fails if user is under 18."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "2020-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 422
    assert "at least 18 years old" in str(response.json())


@pytest.mark.asyncio
async def test_get_profile_success(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving an existing profile."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    response = await client.get(f"/api/v1/accounts/users/{user.id}/profile/")
    assert response.status_code == 200
    assert response.json()["first_name"] == "olena"


@pytest.mark.asyncio
async def test_get_profile_not_found(client, db_session, jwt_manager, seed_user_groups):
    """Test retrieving a profile that doesn't exist."""
    user = await create_regular_user(db_session)

    response = await client.get(f"/api/v1/accounts/users/{user.id}/profile/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


@pytest.mark.asyncio
async def test_update_profile_partial_field(client, db_session, jwt_manager, seed_user_groups):
    """Test that updating one field leaves other fields unchanged."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    response = await client.patch(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={"first_name": "Maria"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "maria"
    assert data["last_name"] == "ivanenko"
    assert data["gender"] == "woman"
    assert data["info"] == "Test bio"


@pytest.mark.asyncio
async def test_update_profile_clear_field(client, db_session, jwt_manager, seed_user_groups):
    """Test that explicitly sending an empty value clears a field."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    response = await client.patch(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={"info": ""},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["info"] is None
    assert data["first_name"] == "olena"


@pytest.mark.asyncio
async def test_update_profile_invalid_gender(client, db_session, jwt_manager, seed_user_groups):
    """Test that updating with invalid gender returns 422 and doesn't change profile."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    response = await client.patch(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={"gender": "invalid_value"},
    )

    assert response.status_code == 422

    get_response = await client.get(f"/api/v1/accounts/users/{user.id}/profile/")
    assert get_response.json()["gender"] == "woman"


@pytest.mark.asyncio
async def test_update_profile_not_found(client, db_session, jwt_manager, seed_user_groups):
    """Test updating a profile that doesn't exist returns 404."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})

    response = await client.patch(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"first_name": "Maria"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_profile_forbidden_for_other_user(client, db_session, jwt_manager, seed_user_groups):
    """Test that a regular user cannot update another user's profile."""
    user1 = await create_regular_user(db_session, email="updateuser1@example.com")
    user2 = await create_regular_user(db_session, email="updateuser2@example.com")
    token1 = jwt_manager.create_access_token({"user_id": user1.id})

    response = await client.patch(
        f"/api/v1/accounts/users/{user2.id}/profile/",
        headers={"Authorization": f"Bearer {token1}"},
        data={"first_name": "Maria"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_profile_avatar_replaces_old(client, db_session, jwt_manager, seed_user_groups, s3_storage_fake):
    """Test that updating the avatar uploads new file and deletes the old one."""
    user = await create_regular_user(db_session)
    access_token = jwt_manager.create_access_token({"user_id": user.id})
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        data={
            "first_name": "Olena", "last_name": "Ivanenko", "gender": "woman",
            "date_of_birth": "1990-05-15", "info": "Test bio",
        },
        files={"avatar": ("old_avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    old_key = f"avatars/{user.id}_old_avatar.jpg"
    assert old_key in s3_storage_fake.storage

    response = await client.patch(
        f"/api/v1/accounts/users/{user.id}/profile/",
        headers=headers,
        files={"avatar": ("new_avatar.jpg", fake_jpeg(), "image/jpeg")},
    )

    assert response.status_code == 200
    new_key = f"avatars/{user.id}_new_avatar.jpg"
    assert new_key in s3_storage_fake.storage
    assert old_key not in s3_storage_fake.storage
