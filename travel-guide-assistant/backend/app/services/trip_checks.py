"""Check a local itinerary against a small, dated catalog of official facts."""
import json
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from app.models.schemas import Itinerary, PlannedStop

CATALOG = json.loads((Path(__file__).resolve().parents[2] / "data" / "verified-places.json").read_text(encoding="utf-8"))


def _key(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


BY_NAME = {_key(name): place for place in CATALOG for name in (place["name"], *place["aliases"])}


def check_trip(itinerary: Itinerary, *, today: date | None = None) -> dict:
    today = today or date.today()
    results, issues = [], []
    total, unchecked, priced = 0, 0, 0
    for day in itinerary.day_plans:
        visit_date = itinerary.start_date + timedelta(days=day.day - 1) if itinerary.start_date else None
        stops = day.stops if day.stops is not None else [PlannedStop(name=name) for name in day.activities if 0 < len(name) <= 500]
        for index, stop in enumerate(stops):
            place = BY_NAME.get(_key(stop.name))
            row = {"day": day.day, "index": index, "name": stop.name, "date": visit_date,
                   "status": "unverified", "visit_time": stop.visit_time}

            def warn(code: str) -> None:
                issues.append({"day": day.day, "index": index, "code": code, "name": stop.name})

            results.append(row)
            if place is None:
                if stop.category in ("ticket", "other"):
                    unchecked += 1
                continue

            row.update(source_url=place["source_url"], verified_on=place["verified_on"])
            row["map_url"] = "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": place["map_query"]})
            if (today - date.fromisoformat(place["verified_on"])).days > 180:
                warn("source_stale")
                unchecked += 1
                continue
            if visit_date and place.get("effective_from") and visit_date.isoformat() < place["effective_from"]:
                warn("outside_source_period")
                unchecked += 1
                continue
            row.update({k: place.get(k) for k in ("opens", "closes", "last_admission", "adult_ticket_jpy")})
            priced += 1
            if itinerary.adult_count is not None:
                total += place["adult_ticket_jpy"] * itinerary.adult_count
            if not visit_date or not stop.visit_time:
                warn("missing_schedule")
            if visit_date and visit_date.strftime("%m-%d") in place["closed_month_days"]:
                row["status"] = "conflict"
                warn("closed")
            elif stop.visit_time and (
                stop.visit_time < place["opens"] or stop.visit_time >= place["closes"]
                or (place.get("last_admission") and stop.visit_time > place["last_admission"])
            ):
                row["status"] = "conflict"
                warn("outside_admission")
            elif visit_date and stop.visit_time:
                row["status"] = "within_published_hours"
    ticket_total = total if priced and itinerary.adult_count is not None else None
    cap = itinerary.attraction_cap_jpy
    if cap is not None and ticket_total is not None and ticket_total > cap:
        issues.append({"code": "ticket_budget_exceeded"})
    return {"stops": results, "issues": issues, "known_ticket_total_jpy": ticket_total,
            "unchecked_ticket_stops": unchecked, "attraction_cap_jpy": cap}
