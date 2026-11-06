import pytest
from sqlalchemy import select

from src.infrastructure.models import User
from tests.conftest import account


def auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_registration_hashing_and_duplicate(client, factory):
    await account(client)
    async with factory() as session:
        user = await session.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert "Safe-Rental" not in user.password_hash
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ALICE@example.com",
            "full_name": "Alice Test",
            "password": "Safe-Rental-Phrase!48",
            "password_confirmation": "Safe-Rental-Phrase!48",
        },
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "password", ["tiny!7", "123456789012", "aaaaaaaaaaaa", " password123456 "]
)
async def test_password_policy_does_not_echo_secrets(client, password):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "full_name": "Alice Test",
            "password": password,
            "password_confirmation": password,
        },
    )
    assert response.status_code == 422
    assert '"input"' not in response.text
    assert password not in response.text


async def test_password_mismatch_and_extra_fields(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "full_name": "Alice Test",
            "password": "Safe-Rental-Phrase!48",
            "password_confirmation": "Different-Phrase!482",
            "is_admin": True,
        },
    )
    assert response.status_code == 422


async def test_login_errors_are_generic(client, tokens):
    first = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"}
    )
    second = await client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"}
    )
    assert first.status_code == second.status_code == 401
    assert first.json() == second.json()


async def test_logout_revokes_access_and_refresh(client, tokens):
    assert (
        await client.get("/api/v1/auth/me", headers=auth(tokens))
    ).status_code == 200
    assert (
        await client.post("/api/v1/auth/logout", headers=auth(tokens))
    ).status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers=auth(tokens))
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
    ).status_code == 401


async def test_refresh_rotation_and_replay_revokes_family(client, tokens):
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401
    assert (
        await client.get("/api/v1/auth/me", headers=auth(rotated))
    ).status_code == 401


async def test_tampered_token_and_missing_auth(client, tokens):
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    tokens["access_token"] = "invalid.jwt.token"
    assert (
        await client.get("/api/v1/auth/me", headers=auth(tokens))
    ).status_code == 401


async def test_body_limit(client):
    result = await client.post(
        "/api/v1/auth/login", content='{"email":"' + "a" * 20000 + '"}'
    )
    assert result.status_code == 413
