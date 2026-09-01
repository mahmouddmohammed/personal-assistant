"""Flight/calendar tools used by the flight_booking ReAct worker.

`book_flight` calls `interrupt()` before it does anything, which is how a
side-effecting tool gets a human checkpoint while the three read-only
tools (search/check/list) run freely.
"""
import datetime
import json
from urllib.parse import quote

from langchain_core.tools import tool
from langgraph.types import interrupt

# Mock flight inventory (kept inline, no file dependency).
FLIGHTS = json.loads(r'''[{"id": "FL101", "origin": "CAI", "destination": "DXB", "date": "2026-08-25", "departure_time": "08:00", "arrival_time": "11:30", "airline": "EgyptAir", "price": 210, "seats_available": 4}, {"id": "FL102", "origin": "CAI", "destination": "DXB", "date": "2026-08-25", "departure_time": "14:15", "arrival_time": "17:45", "airline": "Emirates", "price": 260, "seats_available": 0}, {"id": "FL103", "origin": "CAI", "destination": "DXB", "date": "2026-08-25", "departure_time": "21:00", "arrival_time": "00:30", "airline": "flydubai", "price": 190, "seats_available": 6}, {"id": "FL104", "origin": "CAI", "destination": "DXB", "date": "2026-08-26", "departure_time": "09:30", "arrival_time": "13:00", "airline": "EgyptAir", "price": 205, "seats_available": 5}, {"id": "FL105", "origin": "CAI", "destination": "DXB", "date": "2026-08-26", "departure_time": "18:00", "arrival_time": "21:30", "airline": "Emirates", "price": 275, "seats_available": 2}, {"id": "FL201", "origin": "CAI", "destination": "IST", "date": "2026-08-25", "departure_time": "07:00", "arrival_time": "09:30", "airline": "Turkish Airlines", "price": 150, "seats_available": 3}, {"id": "FL202", "origin": "CAI", "destination": "IST", "date": "2026-08-25", "departure_time": "16:20", "arrival_time": "18:50", "airline": "EgyptAir", "price": 165, "seats_available": 0}, {"id": "FL203", "origin": "CAI", "destination": "IST", "date": "2026-08-27", "departure_time": "10:00", "arrival_time": "12:30", "airline": "Turkish Airlines", "price": 145, "seats_available": 7}, {"id": "FL301", "origin": "JFK", "destination": "LHR", "date": "2026-09-01", "departure_time": "22:00", "arrival_time": "10:00", "airline": "British Airways", "price": 480, "seats_available": 5}, {"id": "FL302", "origin": "JFK", "destination": "LHR", "date": "2026-09-01", "departure_time": "18:30", "arrival_time": "06:30", "airline": "Delta", "price": 510, "seats_available": 0}, {"id": "FL303", "origin": "JFK", "destination": "LHR", "date": "2026-09-02", "departure_time": "21:15", "arrival_time": "09:15", "airline": "Virgin Atlantic", "price": 495, "seats_available": 3}, {"id": "FL401", "origin": "LHR", "destination": "CAI", "date": "2026-09-05", "departure_time": "12:00", "arrival_time": "19:00", "airline": "EgyptAir", "price": 340, "seats_available": 4}, {"id": "FL402", "origin": "LHR", "destination": "CAI", "date": "2026-09-05", "departure_time": "23:45", "arrival_time": "06:45", "airline": "British Airways", "price": 365, "seats_available": 0}]
''')
CALENDAR_EVENTS: list[dict] = []
_next_booking_id = 1


@tool
def search_flights(origin: str = "", destination: str = "", date: str = "") -> dict:
    """Search mock flights by origin/destination IATA code and/or date (YYYY-MM-DD)."""
    origin, destination, date = origin.strip().upper(), destination.strip().upper(), date.strip()
    if not origin and not destination and not date:
        return {"error": "Provide at least one of origin, destination, or date"}

    def matches(f):
        return (not origin or f["origin"] == origin) and (not destination or f["destination"] == destination) \
            and (not date or f["date"] == date)

    matching = [f for f in FLIGHTS if matches(f)]
    available = sorted((f for f in matching if f["seats_available"] > 0), key=lambda f: (f["date"], f["departure_time"]))
    if available:
        return {"status": "available", "flights": available}

    if origin and destination and date:
        same_route = [f for f in FLIGHTS if f["origin"] == origin and f["destination"] == destination]
        if not same_route:
            return {"status": "no_route", "message": f"No flights found for {origin} -> {destination}."}

        def date_distance(f):
            try:
                return abs((datetime.date.fromisoformat(f["date"]) - datetime.date.fromisoformat(date)).days)
            except ValueError:
                return 999

        alternatives = sorted((f for f in same_route if f["seats_available"] > 0), key=date_distance)[:5]
        return {"status": "unavailable", "message": f"No open seats for {origin} -> {destination} on {date}.",
                "alternatives": alternatives}

    if not matching:
        return {"status": "no_route", "message": "No flights found matching those filters."}
    return {"status": "unavailable", "message": "No open seats matching those filters.", "alternatives": []}


def _times_overlap(sa, ea, sb, eb):
    return sa < eb and sb < ea


@tool
def check_calendar_availability(date: str, start_time: str, end_time: str) -> dict:
    """Check whether the mock calendar is free on `date` between `start_time` and `end_time` (HH:MM)."""
    conflicts = [e for e in CALENDAR_EVENTS
                 if e["date"] == date and _times_overlap(start_time, end_time, e["start_time"], e["end_time"])]
    return {"available": len(conflicts) == 0, "conflicts": conflicts}


@tool
def list_calendar_events() -> dict:
    """List all events booked so far in the mock calendar."""
    return {"events": CALENDAR_EVENTS}


def _do_book_flight(flight_id: str, passenger_name: str) -> dict:
    global _next_booking_id
    flight = next((f for f in FLIGHTS if f["id"] == flight_id), None)
    if not flight:
        return {"error": f"Unknown flight_id '{flight_id}'"}
    if flight["seats_available"] <= 0:
        return {"error": f"Flight {flight_id} is sold out. Search again for alternatives."}

    flight["seats_available"] -= 1
    dep = datetime.datetime.fromisoformat(f"{flight['date']}T{flight['departure_time']}")
    arr = datetime.datetime.combine(dep.date(), datetime.datetime.strptime(flight["arrival_time"], "%H:%M").time())
    if arr <= dep:
        arr += datetime.timedelta(days=1)
    event_start, event_end = dep - datetime.timedelta(hours=2), arr

    title = f"Flight {flight_id}: {flight['origin']} to {flight['destination']} ({flight['airline']})"
    details = f"Passenger: {passenger_name} | Departs {flight['departure_time']} | Arrives {flight['arrival_time']} | Price: ${flight['price']}"
    location = f"{flight['origin']} -> {flight['destination']}"
    dates_param = f"{event_start.strftime('%Y%m%dT%H%M%S')}/{event_end.strftime('%Y%m%dT%H%M%S')}"
    calendar_link = ("https://calendar.google.com/calendar/render?action=TEMPLATE"
                      f"&text={quote(title)}&dates={dates_param}&details={quote(details)}&location={quote(location)}")

    booking = {"id": f"BK{_next_booking_id:04d}", "title": title, "date": flight["date"],
               "start_time": event_start.strftime("%H:%M"), "end_time": event_end.strftime("%H:%M"),
               "flight_id": flight_id, "passenger_name": passenger_name, "calendar_link": calendar_link}
    _next_booking_id += 1
    CALENDAR_EVENTS.append(booking)
    return {"status": "booked", "booking": booking}


@tool
def book_flight(flight_id: str, passenger_name: str) -> dict:
    """Book a flight (side-effecting). Pauses for human confirmation first."""
    decision = interrupt({"type": "confirm_booking", "flight_id": flight_id, "passenger_name": passenger_name})
    if decision != "confirm":
        return {"status": "cancelled", "message": "Booking cancelled by user."}
    return _do_book_flight(flight_id, passenger_name)


FLIGHT_TOOLS = [search_flights, check_calendar_availability, list_calendar_events, book_flight]
