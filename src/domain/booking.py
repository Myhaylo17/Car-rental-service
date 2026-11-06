from datetime import date, timedelta
from decimal import Decimal

from src.domain.errors import DomainError


def validate_period(start: date, end: date, today: date) -> None:
    if start < today or start > today + timedelta(days=365):
        raise DomainError(
            422, "invalid_start", "Start must be within the next 365 days."
        )
    if not 1 <= (end - start).days <= 90:
        raise DomainError(
            422, "invalid_period", "Rental duration must be 1 to 90 days."
        )


def rental_total(rate: Decimal, start: date, end: date) -> Decimal:
    return (rate * (end - start).days).quantize(Decimal("0.01"))
