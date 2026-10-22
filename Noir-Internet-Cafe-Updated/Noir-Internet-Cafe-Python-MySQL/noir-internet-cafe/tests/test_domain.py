"""Run without installing anything: python -m unittest discover -s tests -v."""
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("noir_domain", Path(__file__).resolve().parents[1] / "noir" / "domain.py")
domain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(domain)


class BillingTests(unittest.TestCase):
    def test_minimum_one_minute(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(domain.calculate_bill(now, now, Decimal("60")), (1, Decimal("1.00")))

    def test_fractional_minute_rounds_up(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(domain.calculate_bill(now, now + timedelta(seconds=60, microseconds=1), Decimal("60")), (2, Decimal("2.00")))

    def test_exact_hour(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(domain.calculate_bill(now, now + timedelta(hours=1), Decimal("35.50")), (60, Decimal("35.50")))

    def test_money_is_decimal_and_rounds_once(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(domain.calculate_bill(now, now + timedelta(minutes=17), Decimal("35")), (17, Decimal("9.92")))

    def test_backward_clock_does_not_make_negative_invoice(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(domain.calculate_bill(now, now - timedelta(minutes=1), Decimal("60")), (1, Decimal("1.00")))


class ValidationTests(unittest.TestCase):
    def test_rate_validation(self):
        for value in ["0", "-1", "NaN", "Infinity", "100000.01", "1.234", "abc", None]:
            with self.subTest(value=value), self.assertRaises(domain.Problem):
                domain.hourly_rate(value)
        self.assertEqual(domain.hourly_rate("30.50"), Decimal("30.50"))

    def test_email_normalized(self):
        self.assertEqual(domain.email(" Kady@Example.COM "), "kady@example.com")

    def test_invalid_email(self):
        for value in ["x", "a b@example.com", "person@", "@example.com"]:
            with self.subTest(value=value), self.assertRaises(domain.Problem):
                domain.email(value)

    def test_password_length(self):
        with self.assertRaises(domain.Problem):
            domain.password("short")
        self.assertEqual(len(domain.password("x" * 12)), 12)
        with self.assertRaises(domain.Problem):
            domain.password("x" * 129)

    def test_booking_requires_timezone_and_future(self):
        for value in ["2026-01-01T12:00", "invalid", None, "2000-01-01T12:00:00Z"]:
            with self.subTest(value=value), self.assertRaises(domain.Problem):
                domain.booking_time(value)
        future = (domain.utcnow() + timedelta(hours=2)).isoformat() + "Z"
        self.assertIsInstance(domain.booking_time(future), datetime)

    def test_valid_identifiers(self):
        for value in [True, "-1", "1.5", "1 OR 1=1", 0, None]:
            with self.subTest(value=value), self.assertRaises(domain.Problem):
                domain.positive_id(value)
        self.assertEqual(domain.positive_id("23"), 23)

    def test_markup_is_preserved_for_output_escaping(self):
        self.assertEqual(domain.text("<Guest>", "name"), "<Guest>")
        with self.assertRaises(domain.Problem):
            domain.text("bad\nname", "name")


if __name__ == "__main__":
    unittest.main()
