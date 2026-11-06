from tests.test_auth import auth
from tests.test_bookings import book


async def test_filters_search_and_literal_wildcards(client):
    assert (await client.get("/api/v1/cars", params={"q": "Corolla"})).json()[
        "total"
    ] == 1
    assert (await client.get("/api/v1/cars", params={"q": "%"})).json()["total"] == 0
    assert (await client.get("/api/v1/cars", params={"max_price": "1000"})).json()[
        "total"
    ] == 0
    assert (
        await client.get("/api/v1/cars", params={"category": "sedan", "min_seats": 5})
    ).json()["total"] == 1
    assert (
        await client.get(
            "/api/v1/cars", params={"min_price": "2000", "max_price": "1000"}
        )
    ).status_code == 422
    assert (
        await client.get("/api/v1/cars", params={"page_size": 1000})
    ).status_code == 422
    assert (
        await client.get("/api/v1/cars", params={"category": "sql injection"})
    ).status_code == 422


async def test_availability_filter(client, tokens, period):
    assert (await book(client, tokens, period)).status_code == 201
    query = {"start_date": period["start_date"], "end_date": period["end_date"]}
    assert (await client.get("/api/v1/cars", params=query)).json()["total"] == 0
    assert (
        await client.get("/api/v1/cars", params={"start_date": period["start_date"]})
    ).status_code == 422


async def test_favorites_are_idempotent_and_private(client, tokens):
    headers = auth(tokens)
    assert (await client.put("/api/v1/favorites/1", headers=headers)).status_code == 204
    assert (await client.put("/api/v1/favorites/1", headers=headers)).status_code == 204
    assert len((await client.get("/api/v1/favorites", headers=headers)).json()) == 1
    assert (
        await client.delete("/api/v1/favorites/1", headers=headers)
    ).status_code == 204
    assert (
        await client.delete("/api/v1/favorites/1", headers=headers)
    ).status_code == 204
    assert (await client.get("/api/v1/favorites", headers=headers)).json() == []
    assert (
        await client.put("/api/v1/favorites/999", headers=headers)
    ).status_code == 404
