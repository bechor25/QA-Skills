"""Unit tests for app.calc — pure business logic, no I/O."""
from __future__ import annotations

import pytest
from decimal import Decimal

from app.calc import (
    apply_discount,
    calc_tax,
    total_with_tax,
    is_valid_email,
    fizzbuzz,
    money_sum,
)


# ---------------------------------------------------------------------------
# apply_discount
# ---------------------------------------------------------------------------

class TestApplyDiscount:
    def test_zero_discount(self):
        assert apply_discount(100.0, 0) == 100.0

    def test_full_discount(self):
        assert apply_discount(100.0, 100) == 0.0

    def test_partial_discount(self):
        assert apply_discount(200.0, 10) == 180.0

    def test_rounding(self):
        # 1/3 discount on 10 -> 6.666... rounds to 6.67
        result = apply_discount(10.0, 33.333333)
        assert isinstance(result, float)
        assert 6.66 <= result <= 6.68

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            apply_discount(-1.0, 10)

    def test_discount_above_100_raises(self):
        with pytest.raises(ValueError, match="percent"):
            apply_discount(100.0, 101)

    def test_discount_below_0_raises(self):
        with pytest.raises(ValueError, match="percent"):
            apply_discount(100.0, -1)

    def test_zero_price(self):
        assert apply_discount(0.0, 50) == 0.0

    def test_boundary_discount_100(self):
        assert apply_discount(999.99, 100) == 0.0

    def test_small_price(self):
        # 0.01 * (1 - 0.5) = 0.005, round(0.005, 2) = 0.01 in Python (banker's rounding edge)
        assert apply_discount(0.01, 50) == 0.01


# ---------------------------------------------------------------------------
# calc_tax
# ---------------------------------------------------------------------------

class TestCalcTax:
    def test_standard_vat(self):
        assert calc_tax(100.0, 0.17) == 17.0

    def test_zero_rate(self):
        assert calc_tax(100.0, 0.0) == 0.0

    def test_full_rate(self):
        assert calc_tax(100.0, 1.0) == 100.0

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            calc_tax(-1.0, 0.17)

    def test_rate_above_1_raises(self):
        with pytest.raises(ValueError, match="rate"):
            calc_tax(100.0, 1.01)

    def test_rate_below_0_raises(self):
        with pytest.raises(ValueError, match="rate"):
            calc_tax(100.0, -0.01)

    def test_rounding(self):
        # 10.0 * 0.17 = 1.70 exactly
        assert calc_tax(10.0, 0.17) == 1.7

    def test_zero_amount(self):
        assert calc_tax(0.0, 0.17) == 0.0


# ---------------------------------------------------------------------------
# total_with_tax
# ---------------------------------------------------------------------------

class TestTotalWithTax:
    def test_basic_composition(self):
        # 100 -> 10% discount -> 90 -> 17% tax -> 90 + 15.3 = 105.3
        assert total_with_tax(100.0, 10, 0.17) == 105.3

    def test_no_discount_no_tax(self):
        assert total_with_tax(100.0, 0, 0.0) == 100.0

    def test_full_discount(self):
        assert total_with_tax(100.0, 100, 0.17) == 0.0

    def test_default_values(self):
        result = total_with_tax(100.0)
        # default: discount=0, rate=0.17 -> 100 + 17 = 117
        assert result == 117.0

    def test_consistency_with_parts(self):
        price, discount, rate = 250.0, 20.0, 0.10
        discounted = apply_discount(price, discount)
        tax = calc_tax(discounted, rate)
        expected = round(discounted + tax, 2)
        assert total_with_tax(price, discount, rate) == expected


# ---------------------------------------------------------------------------
# is_valid_email
# ---------------------------------------------------------------------------

class TestIsValidEmail:
    @pytest.mark.parametrize("email", [
        "user@example.com",
        "a@b.co",
        "user.name+tag@sub.domain.org",
    ])
    def test_valid_emails(self, email):
        assert is_valid_email(email) is True

    @pytest.mark.parametrize("email", [
        "",
        "notanemail",
        "@nodomain.com",
        "noat",
        "double@@example.com",
        "user@",
        "user@.example.com",
        "user@example.",
        None,
        123,
    ])
    def test_invalid_emails(self, email):
        assert is_valid_email(email) is False


# ---------------------------------------------------------------------------
# fizzbuzz
# ---------------------------------------------------------------------------

class TestFizzbuzz:
    def test_fizz(self):
        assert fizzbuzz(3) == "Fizz"
        assert fizzbuzz(9) == "Fizz"

    def test_buzz(self):
        assert fizzbuzz(5) == "Buzz"
        assert fizzbuzz(10) == "Buzz"

    def test_fizzbuzz(self):
        assert fizzbuzz(15) == "FizzBuzz"
        assert fizzbuzz(30) == "FizzBuzz"

    def test_plain(self):
        assert fizzbuzz(1) == "1"
        assert fizzbuzz(7) == "7"

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="positive"):
            fizzbuzz(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="positive"):
            fizzbuzz(-5)

    def test_boundary_1(self):
        assert fizzbuzz(1) == "1"

    def test_large_fizzbuzz(self):
        assert fizzbuzz(45) == "FizzBuzz"


# ---------------------------------------------------------------------------
# money_sum
# ---------------------------------------------------------------------------

class TestMoneySum:
    def test_simple_sum(self):
        assert money_sum(["1.10", "2.20", "3.30"]) == Decimal("6.60")

    def test_empty_list(self):
        assert money_sum([]) == Decimal("0")

    def test_single_value(self):
        assert money_sum(["9.99"]) == Decimal("9.99")

    def test_no_float_drift(self):
        # 0.1 + 0.2 in float is 0.30000000000000004, Decimal avoids this
        result = money_sum(["0.1", "0.2"])
        assert result == Decimal("0.3")

    def test_large_values(self):
        result = money_sum(["999999.99", "0.01"])
        assert result == Decimal("1000000.00")

    def test_negative_values(self):
        result = money_sum(["-5.00", "10.00"])
        assert result == Decimal("5.00")
