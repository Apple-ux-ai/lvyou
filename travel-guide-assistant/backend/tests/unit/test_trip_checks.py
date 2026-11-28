import unittest
from datetime import date

from app.models.schemas import Itinerary
from app.services.trip_checks import check_trip
from app.services.trips import TripStore


def itinerary(date="2026-12-27", time="17:45", name="大阪城天守阁"):
    return Itinerary.model_validate({
        "destination": "大阪", "days": 1, "start_date": date,
        "adult_count": 2, "attraction_cap_jpy": 2000,
        "day_plans": [{"day": 1, "title": "大阪一日", "transport": "地铁",
                       "stops": [{"name": name, "visit_time": time, "category": "ticket"}]}],
    })


def review(plan):
    return check_trip(plan, today=date(2026, 11, 27))


class TripChecksTests(unittest.TestCase):
    def test_last_admission_and_group_ticket_budget(self):
        result = review(itinerary())
        self.assertEqual(result["known_ticket_total_jpy"], 2400)
        self.assertIn("ticket_budget_exceeded", {x["code"] for x in result["issues"]})
        self.assertIn("outside_admission", {x["code"] for x in result["issues"]})
        self.assertTrue(result["stops"][0]["source_url"].startswith("https://"))

    def test_annual_closure_and_missing_details(self):
        self.assertIn("closed", {x["code"] for x in review(itinerary("2026-12-28"))["issues"]})
        result = review(itinerary(name="未录入景点"))
        self.assertEqual(result["unchecked_ticket_stops"], 1)
        self.assertEqual(result["stops"][0]["status"], "unverified")
        self.assertNotIn("ticket_budget_exceeded", {x["code"] for x in result["issues"]})

    def test_stale_facts_are_not_counted(self):
        result = check_trip(itinerary(), today=date(2028, 1, 1))
        self.assertIsNone(result["known_ticket_total_jpy"])
        self.assertEqual(result["stops"][0]["status"], "unverified")
        self.assertIn("source_stale", {x["code"] for x in result["issues"]})

    def test_boundary_and_park_are_distinct(self):
        self.assertEqual(review(itinerary(time="17:30"))["stops"][0]["status"], "within_published_hours")
        self.assertEqual(review(itinerary(name="大阪城公园"))["stops"][0]["status"], "unverified")
        self.assertEqual(review(itinerary(date=None, time=None))["stops"][0]["status"], "unverified")

    def test_old_and_new_trips_round_trip(self):
        store = TripStore(":memory:")
        try:
            trip = store.create(itinerary())
            self.assertEqual(store.get(trip.id).day_plans[0].stops[0].visit_time, "17:45")
            self.assertEqual(store.get(trip.id).day_plans[0].transport, "地铁")
            old = Itinerary.model_validate({"destination": "京都", "days": 1,
                "day_plans": [{"day": 1, "title": "一天", "activities": ["金阁寺"]}]})
            self.assertEqual(store.create(old).day_plans[0].activities, ["金阁寺"])
        finally:
            store.close()
