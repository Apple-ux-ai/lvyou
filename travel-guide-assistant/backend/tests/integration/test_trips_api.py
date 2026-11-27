"""行程保存 API 集成测试。"""
import pytest
from httpx import ASGITransport, AsyncClient

from app import main as main_module
from app.main import app
from app.services.trips import TripStore


ITINERARY = {
    "destination": "京都",
    "days": 2,
    "total_budget": 3000,
    "day_plans": [],
    "tips": ["提前预约"],
}


@pytest.fixture(autouse=True)
def isolated_trip_store(monkeypatch):
    store = TripStore(":memory:")
    monkeypatch.setattr(main_module, "trip_store", store)
    yield
    store.close()


@pytest.mark.asyncio
async def test_create_trip_returns_an_id_and_persists_it():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/trips", json=ITINERARY)
        assert created.status_code == 201
        payload = created.json()
        assert payload["id"]
        assert payload["destination"] == ITINERARY["destination"]

        fetched = await client.get(f"/api/trips/{payload['id']}")

    assert fetched.status_code == 200
    assert fetched.json() == payload


@pytest.mark.asyncio
async def test_get_trip_returns_404_for_an_unknown_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/trips/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_trips_returns_newest_first():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/trips", json=ITINERARY)
        second = await client.post("/api/trips", json={**ITINERARY, "destination": "奈良"})
        listed = await client.get("/api/trips")

    assert listed.status_code == 200
    assert [trip["id"] for trip in listed.json()] == [second.json()["id"], first.json()["id"]]


@pytest.mark.asyncio
async def test_update_trip_preserves_id_and_returns_new_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/trips", json=ITINERARY)
        updated = await client.put(
            f"/api/trips/{created.json()['id']}",
            json={**ITINERARY, "destination": "大阪", "days": 4},
        )

    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["destination"] == "大阪"
    assert updated.json()["days"] == 4


@pytest.mark.asyncio
async def test_update_trip_returns_404_for_an_unknown_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put("/api/trips/missing", json=ITINERARY)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_trip_rejects_invalid_days():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/trips", json={**ITINERARY, "days": 0})

    assert response.status_code == 422

@pytest.mark.asyncio
async def test_review_does_not_save_and_serializes_dated_stop(monkeypatch):
    from datetime import date
    from app.services.trip_checks import check_trip

    monkeypatch.setattr(main_module, "check_trip", lambda plan: check_trip(plan, today=date(2026, 11, 27)))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.post("/api/trips/check", json={
            **ITINERARY, "start_date": "2026-12-27", "adult_count": 2,
            "day_plans": [{"day": 2, "title": "大阪", "stops": [
                {"name": "大阪城天守阁", "visit_time": "10:00", "category": "ticket"}
            ]}],
        })
        assert result.status_code == 200
        assert result.json()["stops"][0]["date"] == "2026-12-28"
        assert result.json()["issues"][0]["code"] == "closed"
        assert (await client.get("/api/trips")).json() == []
