"""Pure validation and billing rules shared by HTTP endpoints and CLI."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_UP, ROUND_HALF_UP
import re


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def text(value, label, minimum=1, maximum=80):
    if not isinstance(value, str):
        raise Problem(f"Enter a valid {label}.")
    value = value.strip()
    if not minimum <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise Problem(f"{label.capitalize()} must be {minimum}–{maximum} characters.")
    return value


def email(value):
    value = text(value, "email address", 3, 254).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise Problem("Enter a valid email address.")
    return value


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise Problem("Use a password with 12–128 characters.")
    return value


def positive_id(value, label="record"):
    if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= 2147483647:
        raise Problem(f"Choose a valid {label}.")
    return int(value)


def hourly_rate(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not Decimal("0.01") <= amount <= Decimal("100000"):
            raise InvalidOperation
        if amount != amount.quantize(Decimal("0.01")):
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise Problem("Hourly rate must be 0.01–100,000.00, with at most two decimal places.")


def booking_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
    except (ValueError, TypeError, AttributeError):
        raise Problem("Choose a valid booking date and time.")
    delta = (parsed - utcnow()).total_seconds()
    if not 0 < delta <= 30 * 86400:
        raise Problem("Choose a future time within the next 30 days.")
    return parsed


def calculate_bill(started_at, ended_at, rate):
    seconds = Decimal(str(max(0, (ended_at - started_at).total_seconds())))
    minutes = max(1, int((seconds / 60).to_integral_value(rounding=ROUND_UP)))
    amount = (Decimal(rate) * minutes / 60).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return minutes, amount


def session_duration(value):
    if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= 1440:
        raise Problem("Session time must be a whole number from 1 to 1,440 minutes.")
    return int(value)
