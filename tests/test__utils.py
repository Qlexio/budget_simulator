"""Tests for _utils.py — quantize_amount and to_decimal."""

import pytest
from decimal import Decimal

from _utils import quantize_amount, to_decimal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def five_places():
    """The five-decimal-place precision used for rates."""
    return "0.00001"


# ===========================================================================
# quantize_amount
# ===========================================================================

class TestQuantizeAmount:
    """Tests for quantize_amount(value: Decimal) -> Decimal."""

    def test_truncates_beyond_two_dp(self):
        """Extra decimal places are rounded, not silently truncated."""
        assert quantize_amount(Decimal("9.999")) == Decimal("10.00")

    def test_negative_value_two_dp(self):
        """Negative values are quantized correctly."""
        assert quantize_amount(Decimal("-7.5")) == Decimal("-7.50")

    def test_large_value_preserves_magnitude(self):
        """Very large monetary values are quantized without losing magnitude."""
        assert quantize_amount(Decimal("999999999.999")) == Decimal("1000000000.00")

    def test_exponent_is_minus_two(self):
        """The internal exponent of the result must be exactly -2."""
        assert quantize_amount(Decimal("42.1")).as_tuple().exponent == -2

    @pytest.mark.parametrize("raw,expected", [
        ("0",    "0.00"),     # zero without trailing zeros → gains .00
        ("0.00", "0.00"),     # zero already at 2 d.p.
        ("0.01", "0.01"),     # already at 2 d.p., unchanged
        ("100",  "100.00"),   # integer-valued Decimal, no trailing zeros → gains .00
        ("100.00", "100.00"), # integer value already at 2 d.p.
        ("0.009", "0.01"),    # rounds up (above midpoint)
        ("0.005", "0.00"),    # ROUND_HALF_EVEN: 0 is even → rounds down
        ("0.015", "0.02"),    # ROUND_HALF_EVEN: 2 is even → rounds up
        ("-0.005", "0.00"),   # ROUND_HALF_EVEN on negative
        ("-0.015", "-0.02"),  # ROUND_HALF_EVEN on negative
    ])
    def test_parametrized_rounding_boundaries(self, raw, expected):
        """Boundary-value table for ROUND_HALF_EVEN at 2 d.p."""
        assert quantize_amount(Decimal(raw)) == Decimal(expected)

    def test_non_decimal_input_raises_type_error(self):
        """Passing a non-Decimal (e.g. float) raises TypeError; callers must use to_decimal first."""
        with pytest.raises(TypeError, match="Expected Decimal"):
            quantize_amount(3.14)  # type: ignore[arg-type]


# ===========================================================================
# to_decimal
# ===========================================================================

class TestToDecimal:
    """Tests for to_decimal(value, precision='0.01') -> Decimal."""

    def test_float_representation_hazard_avoided(self):
        """0.1 + 0.2 == 0.30000000000000004 in binary float; str() conversion
        must still produce 0.30 because Python's str(0.1 + 0.2) gives '0.3'."""
        assert to_decimal(0.1 + 0.2) == Decimal("0.30")

    def test_float_with_many_decimal_places_is_rounded(self):
        """A float with more decimal places than precision is rounded.
        str(1.005)=='1.005'; ROUND_HALF_EVEN on digit 0 (even) → rounds down to 1.00."""
        assert to_decimal(1.005) == Decimal("1.00")

    def test_large_int_converts(self):
        """Large loan amounts convert without overflow."""
        assert to_decimal(1_000_000) == Decimal("1000000.00")

    def test_custom_precision_five_dp(self, five_places):
        """Rate precision '0.00001' keeps five decimal places."""
        result = to_decimal(0.0375, precision=five_places)
        assert result == Decimal("0.03750")
        assert result.as_tuple().exponent == -5

    def test_rate_very_small_value(self, five_places):
        """A very small insurance rate (0.036%) converts without underflow."""
        assert to_decimal(0.00036, precision=five_places) == Decimal("0.00036")

    @pytest.mark.parametrize("value,precision,expected", [
        (0,       "0.01",    "0.00"),
        (1,       "0.01",    "1.00"),
        (-1,      "0.01",    "-1.00"),
        (0.1,     "0.01",    "0.10"),
        (0.15,    "0.1",     "0.2"),   # ROUND_HALF_EVEN: 2 is even
        (0.25,    "0.1",     "0.2"),   # ROUND_HALF_EVEN: 2 is even
        (0.35,    "0.1",     "0.4"),   # ROUND_HALF_EVEN: 4 is even
        (1000,    "0.01",    "1000.00"),
        (0.00001, "0.00001", "0.00001"),
    ])
    def test_parametrized_conversions(self, value, precision, expected):
        """Parametrized truth table across types, precisions, and boundaries."""
        assert to_decimal(value, precision=precision) == Decimal(expected)

    def test_non_numeric_input_raises_type_error(self):
        """A non-int/float value raises TypeError with a descriptive message."""
        with pytest.raises(TypeError, match="Expected int or float"):
            to_decimal("abc")  # type: ignore[arg-type]

    def test_invalid_precision_string_raises_value_error(self):
        """A non-numeric precision string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid precision string"):
            to_decimal(1.0, precision="")
