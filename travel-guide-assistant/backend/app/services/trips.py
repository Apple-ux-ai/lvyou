"""SQLite-backed storage for saved itineraries."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.schemas import Itinerary, Trip


class TripStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[2] / "data" / "trips.db"
        self.db_path = str(db_path or os.getenv("TRAVELMATE_DB_PATH") or default_path)
        self._connection: sqlite3.Connection | None = None
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _initialize(self) -> None:
        connection = self._connect()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trips (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.commit()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _to_trip(row: sqlite3.Row) -> Trip:
        payload = json.loads(row["payload"])
        return Trip(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            **payload,
        )

    def _find_row(self, trip_id: str) -> sqlite3.Row | None:
        return self._connect().execute(
            "SELECT id, created_at, updated_at, payload FROM trips WHERE id = ?",
            (trip_id,),
        ).fetchone()

    def create(self, itinerary: Itinerary) -> Trip:
        now = self._now()
        trip = Trip(id=uuid4().hex, created_at=now, updated_at=now, **itinerary.model_dump())
        self._connect().execute(
            "INSERT INTO trips (id, created_at, updated_at, payload) VALUES (?, ?, ?, ?)",
            (
                trip.id,
                trip.created_at.isoformat(),
                trip.updated_at.isoformat(),
                json.dumps(itinerary.model_dump(mode="json"), ensure_ascii=False),
            ),
        )
        self._connect().commit()
        return trip

    def list(self) -> list[Trip]:
        rows = self._connect().execute(
            "SELECT id, created_at, updated_at, payload FROM trips ORDER BY updated_at DESC, rowid DESC"
        ).fetchall()
        return [self._to_trip(row) for row in rows]

    def get(self, trip_id: str) -> Trip | None:
        row = self._find_row(trip_id)
        return self._to_trip(row) if row else None

    def update(self, trip_id: str, itinerary: Itinerary) -> Trip | None:
        existing = self._find_row(trip_id)
        if existing is None:
            return None

        updated = Trip(
            id=trip_id,
            created_at=datetime.fromisoformat(existing["created_at"]),
            updated_at=self._now(),
            **itinerary.model_dump(),
        )
        self._connect().execute(
            "UPDATE trips SET updated_at = ?, payload = ? WHERE id = ?",
            (
                updated.updated_at.isoformat(),
                json.dumps(itinerary.model_dump(mode="json"), ensure_ascii=False),
                trip_id,
            ),
        )
        self._connect().commit()
        return updated

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


trip_store = TripStore()
