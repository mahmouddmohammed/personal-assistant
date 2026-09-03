"""Flight/calendar tools used by the flight_booking ReAct worker."""
import datetime
import json
import logging
from urllib.parse import quote

from langchain_core.tools import tool
from langgraph.types import interrupt

from app.db.session import SessionLocal
from app.repositories.booking_repository import BookingRepository

logger = logging.getLogger(__name__)


FLIGHTS = json.loads(r'''[{"id": "FL101", "origin": "CAI", "destination": "DXB", "date": "2026-08-25", "departure_time": "08:00", "arrival_time": "11:30", "airline": "EgyptAir", "price": 210, "seats_available": 4}, {"id": "FL102", "origin": "CAI", "destination": "DXB", "date": "2026-08-25", "departure_time": "14:15", "arrival_time": "17:45", "airline": "Emirates", "price": 260, "seats_available": 0}, {"id": "FL103", "origin": "CAI", "destination": "DXB", "date": "2026-08-25", "departure_time": "21:00", "arrival_time": "00:30", "airline": "flydubai", "price": 190, "seats_available": 6}, {"id": "FL104", "origin": "CAI", "destination": "DXB", "date": "2026-08-26", "departure_time": "09:30", "arrival_time": "13:00", "airline": "EgyptAir", "price": 205, "seats_available": 5}, {"id": "FL105", "origin": "CAI", "destination": "DXB", "date": "2026-08-26", "departure_time": "18:00", "arrival_time": "21:30", "airline": "Emirates", "price": 275, "seats_available": 2}, {"id": "FL201", "origin": "CAI", "destination": "IST", "date": "2026-08-25", "departure_time": "07:00", "arrival_time": "09:30", "airline": "Turkish Airlines", "price": 150, "seats_available": 3}, {"id": "FL202", "origin": "CAI", "destination": "IST", "date": "2026-08-25", "departure_time": "16:20", "arrival_time": "18:50", "airline": "EgyptAir", "price": 165, "seats_available": 0}, {"id": "FL203", "origin": "CAI", "destination": "IST", "date": "2026-08-27", "departure_time": "10:00", "arrival_time": "12:30", "airline": "Turkish Airlines", "price": 145, "seats_available": 7}, {"id": "FL301", "origin": "JFK", "destination": "LHR", "date": "2026-09-01", "departure_time": "22:00", "arrival_time": "10:00", "airline": "British Airways", "price": 480, "seats_available": 5}, {"id": "FL302", "origin": "JFK", "destination": "LHR", "date": "2026-09-01", "departure_time": "18:30", "arrival_time": "06:30", "airline": "Delta", "price": 510, "seats_available": 0}, {"id": "FL303", "origin": "JFK", "destination": "LHR", "date": "2026-09-02", "departure_time": "21:15", "arrival_time": "09:15", "airline": "Virgin Atlantic", "price": 495, "seats_available": 3}, {"id": "FL401", "origin": "LHR", "destination": "CAI", "date": "2026-09-05", "departure_time": "12:00", "arrival_time": "19:00", "airline": "EgyptAir", "price": 340, "seats_available": 4}, {"id": "FL402", "origin": "LHR", "destination": "CAI", "date": "2026-09-05", "departure_time": "23:45", "arrival_time": "06:45", "airline": "British Airways", "price": 365, "seats_available": 0}]
''')


def _find_flight(flight_id: str) -> dict | None:
    return next((f for f in FLIGHTS if f["id"] == flight_id), None)


def _times_overlap(sa, ea, sb, eb):
    return sa < eb and sb < ea


def _event_window(flight: dict) -> tuple[datetime.datetime, datetime.datetime]:
    dep = datetime.datetime.fromisoformat(f"{flight['date']}T{flight['departure_time']}")
    arr = datetime.datetime.combine(dep.date(), datetime.datetime.strptime(flight["arrival_time"], "%H:%M").time())
    if arr <= dep:
        arr += datetime.timedelta(days=1)
    return dep - datetime.timedelta(hours=2), arr


def _calendar_link(flight_id: str, flight: dict, passenger_name: str, event_start, event_end) -> str:
    title = f"Flight {flight_id}: {flight['origin']} to {flight['destination']} ({flight['airline']})"
    details = f"Passenger: {passenger_name} | Departs {flight['departure_time']} | Arrives {flight['arrival_time']} | Price: ${flight['price']}"
    location = f"{flight['origin']} -> {flight['destination']}"
    dates_param = f"{event_start.strftime('%Y%m%dT%H%M%S')}/{event_end.strftime('%Y%m%dT%H%M%S')}"
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(title)}&dates={dates_param}&details={quote(details)}&location={quote(location)}")


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


def build_flight_tools(user_id: str, conversation_id: str | None = None) -> list:
    """Builds the per-invocation, user-bound tool set. Called once per
    flight_booking subgraph run (see workers/flight_booking.py), not
    cached globally, since `user_id` differs per call and must never be an
    LLM-controlled argument."""

    @tool
    def check_calendar_availability(date: str, start_time: str, end_time: str) -> dict:
        """Check whether this user's calendar is free on `date` between `start_time` and `end_time` (HH:MM)."""
        db = SessionLocal()
        try:
            bookings = BookingRepository(db).list_active_for_user(user_id)
            conflicts = []
            for b in bookings:
                flight = _find_flight(b.flight_id)
                if not flight or b.date != date:
                    continue
                event_start, event_end = _event_window(flight)
                if _times_overlap(start_time, end_time, event_start.strftime("%H:%M"), event_end.strftime("%H:%M")):
                    conflicts.append({"booking_ref": b.booking_ref, "flight_id": b.flight_id,
                                       "start_time": event_start.strftime("%H:%M"), "end_time": event_end.strftime("%H:%M")})
            return {"available": len(conflicts) == 0, "conflicts": conflicts}
        finally:
            db.close()

    @tool
    def list_calendar_events() -> dict:
        """List this user's confirmed flight bookings."""
        db = SessionLocal()
        try:
            bookings = BookingRepository(db).list_active_for_user(user_id)
            return {"events": [
                {"booking_ref": b.booking_ref, "flight_id": b.flight_id, "date": b.date,
                 "departure_time": b.departure_time, "arrival_time": b.arrival_time,
                 "origin": b.origin, "destination": b.destination, "airline": b.airline,
                 "passenger_name": b.passenger_name, "calendar_link": b.calendar_link}
                for b in bookings
            ]}
        finally:
            db.close()

    @tool(response_format="content_and_artifact")
    def book_flight(flight_id: str, passenger_name: str):
        """Book a flight (side-effecting). Pauses for human confirmation first."""
        decision = interrupt({"type": "confirm_booking", "flight_id": flight_id, "passenger_name": passenger_name})
        if decision != "confirm":
            return "Booking cancelled by user.", {"status": "cancelled"}

        flight = _find_flight(flight_id)
        if not flight:
            return f"Unknown flight_id '{flight_id}'", {"status": "error"}
        if flight["seats_available"] <= 0:
            return f"Flight {flight_id} is sold out. Search again for alternatives.", {"status": "error"}

        db = SessionLocal()
        try:
            repo = BookingRepository(db)
            flight["seats_available"] -= 1
            event_start, event_end = _event_window(flight)
            link = _calendar_link(flight_id, flight, passenger_name, event_start, event_end)
            from app.models.booking import Booking
            booking = Booking(
                user_id=user_id, conversation_id=conversation_id, booking_ref=repo.next_ref(),
                flight_id=flight_id, passenger_name=passenger_name, origin=flight["origin"],
                destination=flight["destination"], date=flight["date"], departure_time=flight["departure_time"],
                arrival_time=flight["arrival_time"], airline=flight["airline"], price=flight["price"],
                status="confirmed", calendar_link=link,
            )
            repo.add(booking)
            data = {"status": "booked", "booking": {
                "id": booking.booking_ref, "flight_id": flight_id, "date": flight["date"],
                "start_time": event_start.strftime("%H:%M"), "end_time": event_end.strftime("%H:%M"),
                "passenger_name": passenger_name, "calendar_link": link,
            }}
            return f"Booked {flight_id} for {passenger_name}, confirmation {booking.booking_ref}.", data
        except Exception:
            logger.exception("book_flight: failed to persist booking for user %s", user_id)
            flight["seats_available"] += 1
            return "Sorry, something went wrong saving the booking. Please try again.", {"status": "error"}
        finally:
            db.close()

    @tool(response_format="content_and_artifact")
    def cancel_flight(booking_ref: str):
        """Cancel one of this user's existing confirmed bookings by its
        booking_ref (e.g. 'BK0007'). Get booking_ref from list_calendar_events
        if you don't already have it from the conversation. Pauses for human
        confirmation first — never assume, always confirm which one."""
        decision = interrupt({"type": "confirm_cancel_booking", "booking_ref": booking_ref})
        if decision != "confirm":
            return "Cancellation aborted by user; booking kept.", {"status": "kept"}

        db = SessionLocal()
        try:
            repo = BookingRepository(db)
            booking = repo.get_by_ref_for_user(booking_ref, user_id)
            if not booking or booking.status != "confirmed":
                return f"No active booking found with reference '{booking_ref}'.", {"status": "error"}
            booking.status = "cancelled"
            db.add(booking)
            db.commit()
            flight = _find_flight(booking.flight_id)
            if flight:
                flight["seats_available"] += 1
            return f"Cancelled booking {booking_ref} ({booking.flight_id}).", {"status": "cancelled", "booking_ref": booking_ref}
        except Exception:
            logger.exception("cancel_flight: failed to cancel booking %s for user %s", booking_ref, user_id)
            return "Sorry, something went wrong cancelling that booking. Please try again.", {"status": "error"}
        finally:
            db.close()

    @tool(response_format="content_and_artifact")
    def modify_flight(booking_ref: str, new_flight_id: str):
        """Change an existing confirmed booking to a different flight_id
        (e.g. a different date/time found via search_flights). Pauses for
        human confirmation first. Internally cancels the old booking and
        creates a new one under the same passenger name."""
        decision = interrupt({"type": "confirm_modify_booking", "booking_ref": booking_ref, "new_flight_id": new_flight_id})
        if decision != "confirm":
            return "Change aborted by user; original booking kept.", {"status": "kept"}

        new_flight = _find_flight(new_flight_id)
        if not new_flight:
            return f"Unknown flight_id '{new_flight_id}'", {"status": "error"}
        if new_flight["seats_available"] <= 0:
            return f"Flight {new_flight_id} is sold out. Search again for alternatives.", {"status": "error"}

        db = SessionLocal()
        try:
            repo = BookingRepository(db)
            old = repo.get_by_ref_for_user(booking_ref, user_id)
            if not old or old.status != "confirmed":
                return f"No active booking found with reference '{booking_ref}'.", {"status": "error"}

            old_flight = _find_flight(old.flight_id)
            old.status = "cancelled"
            db.add(old)
            if old_flight:
                old_flight["seats_available"] += 1

            new_flight["seats_available"] -= 1
            event_start, event_end = _event_window(new_flight)
            link = _calendar_link(new_flight_id, new_flight, old.passenger_name, event_start, event_end)
            from app.models.booking import Booking
            new_booking = Booking(
                user_id=user_id, conversation_id=conversation_id, booking_ref=repo.next_ref(),
                flight_id=new_flight_id, passenger_name=old.passenger_name, origin=new_flight["origin"],
                destination=new_flight["destination"], date=new_flight["date"],
                departure_time=new_flight["departure_time"], arrival_time=new_flight["arrival_time"],
                airline=new_flight["airline"], price=new_flight["price"], status="confirmed", calendar_link=link,
            )
            repo.add(new_booking)
            data = {"status": "booked", "booking": {
                "id": new_booking.booking_ref, "flight_id": new_flight_id, "date": new_flight["date"],
                "start_time": event_start.strftime("%H:%M"), "end_time": event_end.strftime("%H:%M"),
                "passenger_name": old.passenger_name, "calendar_link": link,
            }}
            return f"Moved booking {booking_ref} to {new_flight_id}; new confirmation {new_booking.booking_ref}.", data
        except Exception:
            logger.exception("modify_flight: failed to modify booking %s for user %s", booking_ref, user_id)
            db.rollback()
            return "Sorry, something went wrong changing that booking. Please try again.", {"status": "error"}
        finally:
            db.close()

    return [search_flights, check_calendar_availability, list_calendar_events,
            book_flight, cancel_flight, modify_flight]
