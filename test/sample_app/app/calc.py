"""Pure business logic — primary target for unit-test skill.

Functions: deterministic, no I/O, easy to cover w/ boundary + edge cases.
"""
from __future__ import annotations

from decimal import Decimal


def apply_discount(price: float, percent: float) -> float:
    """Return price after percent discount. percent in [0, 100]."""
    if price < 0:
        raise ValueError("price must be non-negative")
    if not 0 <= percent <= 100:
        raise ValueError("percent must be in [0, 100]")
    return round(price * (1 - percent / 100), 2)


def calc_tax(amount: float, rate: float = 0.17) -> float:
    """VAT-style tax. rate in [0, 1]."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not 0 <= rate <= 1:
        raise ValueError("rate must be in [0, 1]")
    return round(amount * rate, 2)


def total_with_tax(price: float, discount_pct: float = 0, tax_rate: float = 0.17) -> float:
    """Compose discount + tax — the canonical happy-path."""
    discounted = apply_discount(price, discount_pct)
    return round(discounted + calc_tax(discounted, tax_rate), 2)


def is_valid_email(value: str) -> bool:
    """Cheap email validator. Boundary cases: empty, no @, multiple @, leading dot."""
    if not value or not isinstance(value, str):
        return False
    if value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    if not local or not domain:
        return False
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False
    return True


def fizzbuzz(n: int) -> str:
    if n <= 0:
        raise ValueError("n must be positive")
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)


def money_sum(values: list[str]) -> Decimal:
    """Sum monetary strings using Decimal to avoid float drift."""
    total = Decimal("0")
    for v in values:
        total += Decimal(v)
    return total
