from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.repositories.base_repository import BaseRepository


class BookingRepository(BaseRepository[Booking]):
    model = Booking

    def list_active_for_user(self, user_id: str) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(Booking.user_id == user_id, Booking.status == "confirmed")
            .order_by(Booking.date.asc(), Booking.departure_time.asc())
        )
        return list(self.db.scalars(stmt))

    def get_by_ref_for_user(self, booking_ref: str, user_id: str) -> Booking | None:
        """Scoped by user_id on purpose -- a booking_ref the LLM produces
        must never let one user touch another user's booking, even if the
        ref itself were guessed or hallucinated correctly."""
        stmt = select(Booking).where(Booking.booking_ref == booking_ref, Booking.user_id == user_id)
        return self.db.scalars(stmt).first()

    def next_ref(self) -> str:
        """Generates the next human-speakable booking reference.

        The bug came from generating booking_ref using Booking.count(), which allowed concurrent bookings to calculate the same reference and trigger a raw IntegrityError
        Generate the reference in a loop, skipping any already-existing refs. This prevents common multi-tab/low-traffic collisions and allows a friendly retry, though a DB-level sequence would still be needed for heavy concurrency.
        """
        count = self.db.query(Booking).count()
        while True:
            candidate = f"BK{count + 1:04d}"
            exists = self.db.query(Booking.id).filter(Booking.booking_ref == candidate).first()
            if not exists:
                return candidate
            count += 1


def get_booking_repository(db: Session) -> BookingRepository:
    return BookingRepository(db)
