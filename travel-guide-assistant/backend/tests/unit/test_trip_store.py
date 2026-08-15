from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from app.models.schemas import Itinerary
from app.services.trips import TripStore


@pytest.fixture
def database_path():
    test_root = Path(__file__).resolve().parent / ".trip-store-tests" / uuid4().hex
    test_root.mkdir(parents=True)
    try:
        yield test_root / "trips.db"
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_trip_store_persists_updates_across_instances(database_path):
    itinerary = Itinerary(
        destination="Kyoto",
        days=3,
        total_budget=4200,
        day_plans=[],
        tips=["Book popular restaurants ahead"],
    )

    store = TripStore(database_path)
    created = store.create(itinerary)
    updated = store.update(
        created.id,
        Itinerary(
            destination="Kyoto",
            days=4,
            total_budget=5000,
            day_plans=[],
            tips=["Book popular restaurants ahead", "Use an IC card"],
        ),
    )
    store.close()

    reopened = TripStore(database_path)
    assert reopened.get(created.id) == updated
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    reopened.close()


def test_trip_store_lists_newest_updates_first(database_path):
    store = TripStore(database_path)
    first = store.create(Itinerary(destination="Osaka", days=2, day_plans=[]))
    second = store.create(Itinerary(destination="Nara", days=1, day_plans=[]))

    trips = store.list()

    assert [trip.id for trip in trips] == [second.id, first.id]
    store.close()


def test_trip_store_uses_creation_order_when_timestamps_match(database_path, monkeypatch):
    store = TripStore(database_path)
    fixed_time = datetime(2026, 8, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(store, "_now", lambda: fixed_time)

    first = store.create(Itinerary(destination="Osaka", days=2, day_plans=[]))
    second = store.create(Itinerary(destination="Nara", days=1, day_plans=[]))

    assert [trip.id for trip in store.list()] == [second.id, first.id]
    store.close()


def test_trip_store_update_returns_none_for_unknown_id(database_path):
    store = TripStore(database_path)

    assert store.update("missing", Itinerary(destination="Osaka", days=1, day_plans=[])) is None

    store.close()
