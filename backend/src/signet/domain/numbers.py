"""Numeric validation shared by domain values and their canonical encoding."""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

# Bound fixed-point output before formatting untrusted scientific notation.
# This comfortably covers finite float quotes and protocol-sized XRP values.
MAX_DECIMAL_COMPONENT_SIZE = 1024


def decimal_value(value: object, name: str = "value", *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'numeric'}")
    parts = result.as_tuple()
    expanded_digits = len(parts.digits) + max(0, parts.exponent)
    if expanded_digits > MAX_DECIMAL_COMPONENT_SIZE or abs(parts.exponent) > MAX_DECIMAL_COMPONENT_SIZE:
        raise ValueError(f"{name} exceeds the supported numeric size")
    return result


def positive_float(value: object, name: str = "value") -> float:
    number = float(decimal_value(value, name, positive=True))
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def decimal_text(value: object) -> str:
    number = decimal_value(value)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if number == 0 else text
