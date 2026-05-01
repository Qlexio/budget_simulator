"""Tests for _utils.py — quantize_amount and to_decimal.

Green tests verify correct, expected behaviour.
Red (xfail) tests document known gaps: inputs the functions do not guard
against, or behaviour that may surprise callers.
"""

import pytest
from decimal import Decimal

from _utils import quantize_amount, to_decimal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_places():
    """The canonical two-decimal-place quantizer string."""
    return "0.01"


@pytest.fixture
def five_places():
    """The five-decimal-place precision used for rates."""
    return "0.00001"


# ===========================================================================
# quantize_amount
# ===========================================================================

class TestQuantizeAmount:
    """Tests for quantize_amount(value: Decimal) -> Decimal."""

    # -----------------------------------------------------------------------
    # GREEN — happy paths
    # -----------------------------------------------------------------------

    def test_already_two_dp_unchanged(self):
        """A value already at 2 d.p. is returned as-is."""
        assert quantize_amount(Decimal("12.34")) == Decimal("12.34")

    def test_zero_returns_zero_with_two_dp(self):
        """Zero is quantized to 0.00."""
        result = quantize_amount(Decimal("0"))
        assert result == Decimal("0.00")
        assert result.as_tuple().exponent == -2

    def test_positive_integer_decimal_gets_two_dp(self):
        """An integer-valued Decimal gains a .00 suffix."""
        result = quantize_amount(Decimal("100"))
        assert result == Decimal("100.00")

    def test_rounds_half_up_on_third_dp(self):
        """Values at exactly .005 round up (ROUND_HALF_EVEN is Python default,
        so .005 rounds to .00 for even and .01 for odd — we assert the Decimal
        default rounding behaviour is preserved unchanged by the wrapper)."""
        result = quantize_amount(Decimal("1.235"))
        # Decimal default is ROUND_HALF_EVEN → 1.235 rounds to 1.24
        assert result == Decimal("1.24")

    def test_truncates_beyond_two_dp(self):
        """Extra decimal places are rounded, not silently truncated."""
        result = quantize_amount(Decimal("9.999"))
        assert result == Decimal("10.00")

    def test_negative_value_two_dp(self):
        """Negative values are quantized correctly."""
        assert quantize_amount(Decimal("-7.5")) == Decimal("-7.50")

    def test_negative_rounds_toward_even(self):
        """Negative values round using the same ROUND_HALF_EVEN rule."""
        result = quantize_amount(Decimal("-1.235"))
        assert result == Decimal("-1.24")

    def test_large_value_preserves_magnitude(self):
        """Very large monetary values are quantized without losing magnitude."""
        result = quantize_amount(Decimal("999999999.999"))
        assert result == Decimal("1000000000.00")

    def test_small_fractional_value_rounds_to_zero(self):
        """A sub-cent value rounds down to zero."""
        assert quantize_amount(Decimal("0.004")) == Decimal("0.00")

    def test_small_fractional_value_rounds_up_to_one_cent(self):
        """A value just above 0.005 rounds up to one cent."""
        assert quantize_amount(Decimal("0.006")) == Decimal("0.01")

    def test_return_type_is_decimal(self):
        """Return type must be Decimal, not float or str."""
        result = quantize_amount(Decimal("3.14159"))
        assert isinstance(result, Decimal)

    def test_exponent_is_minus_two(self):
        """The internal exponent of the result must be exactly -2."""
        result = quantize_amount(Decimal("42.1"))
        assert result.as_tuple().exponent == -2

    @pytest.mark.parametrize("raw,expected", [
        ("0.00",   "0.00"),
        ("0.01",   "0.01"),
        ("0.009",  "0.01"),
        ("0.005",  "0.00"),   # ROUND_HALF_EVEN: 0 is even
        ("0.015",  "0.02"),   # ROUND_HALF_EVEN: 2 is even
        ("100.00", "100.00"),
        ("-0.005", "0.00"),   # ROUND_HALF_EVEN on negative
        ("-0.015", "-0.02"),
    ])
    def test_parametrized_rounding_boundaries(self, raw, expected):
        """Boundary-value table for ROUND_HALF_EVEN at 2 d.p."""
        assert quantize_amount(Decimal(raw)) == Decimal(expected)

    # -----------------------------------------------------------------------
    # Type guard — wrong input types raise TypeError
    # -----------------------------------------------------------------------

    def test_float_input_raises_type_error(self):
        """Passing a raw float raises TypeError; callers must use to_decimal first."""
        with pytest.raises(TypeError, match="Expected Decimal"):
            quantize_amount(3.14)  # type: ignore[arg-type]

    def test_int_input_raises_type_error(self):
        """Passing a raw int raises TypeError."""
        with pytest.raises(TypeError, match="Expected Decimal"):
            quantize_amount(5)  # type: ignore[arg-type]

    def test_none_input_raises_type_error(self):
        """Passing None raises TypeError."""
        with pytest.raises(TypeError, match="Expected Decimal"):
            quantize_amount(None)  # type: ignore[arg-type]

    def test_string_input_raises_type_error(self):
        """Passing a string raises TypeError; callers must use to_decimal first."""
        with pytest.raises(TypeError, match="Expected Decimal"):
            quantize_amount("3.14")  # type: ignore[arg-type]


# ===========================================================================
# to_decimal
# ===========================================================================

class TestToDecimal:
    """Tests for to_decimal(value, precision='0.01') -> Decimal."""

    # -----------------------------------------------------------------------
    # GREEN — happy paths
    # -----------------------------------------------------------------------

    def test_int_converts_to_decimal_two_dp(self):
        """An integer is converted to a two-d.p. Decimal."""
        assert to_decimal(5) == Decimal("5.00")

    def test_int_zero_converts_to_zero(self):
        """Zero integer becomes 0.00."""
        assert to_decimal(0) == Decimal("0.00")

    def test_negative_int_converts(self):
        """Negative integer converts correctly."""
        assert to_decimal(-3) == Decimal("-3.00")

    def test_float_simple_converts(self):
        """A simple float like 1.5 round-trips cleanly."""
        assert to_decimal(1.5) == Decimal("1.50")

    def test_float_representation_hazard_avoided(self):
        """0.1 + 0.2 == 0.30000000000000004 in binary float; str() conversion
        must still produce 0.30 because Python's str(0.1 + 0.2) gives '0.3'."""
        result = to_decimal(0.1 + 0.2)
        assert result == Decimal("0.30")

    def test_float_that_is_exact_in_binary(self):
        """0.25 is exact in IEEE-754; result must be 0.25."""
        assert to_decimal(0.25) == Decimal("0.25")

    def test_float_with_many_decimal_places_is_rounded(self):
        """A float with more decimal places than precision is rounded."""
        assert to_decimal(1.005) == Decimal("1.00")  # str(1.005)=='1.005' → rounds to 1.00 (ROUND_HALF_EVEN)

    def test_return_type_is_decimal(self):
        """Return type must be Decimal."""
        assert isinstance(to_decimal(42), Decimal)

    def test_default_precision_is_two_dp(self, two_places):
        """Default precision is '0.01' — result exponent is -2."""
        result = to_decimal(7)
        assert result.as_tuple().exponent == -2

    def test_large_int_converts(self):
        """Large loan amounts convert without overflow."""
        result = to_decimal(1_000_000)
        assert result == Decimal("1000000.00")

    def test_large_float_converts(self):
        """A large float representing a loan amount converts correctly."""
        result = to_decimal(250_000.50)
        assert result == Decimal("250000.50")

    # -----------------------------------------------------------------------
    # GREEN — custom precision
    # -----------------------------------------------------------------------

    def test_custom_precision_five_dp(self, five_places):
        """Rate precision '0.00001' keeps five decimal places."""
        result = to_decimal(0.0375, precision=five_places)
        assert result == Decimal("0.03750")
        assert result.as_tuple().exponent == -5

    def test_custom_precision_zero_dp(self):
        """Precision '1' truncates to whole number."""
        result = to_decimal(9.9, precision="1")
        assert result == Decimal("10")

    def test_custom_precision_four_dp(self):
        """Precision '0.0001' keeps four decimal places."""
        result = to_decimal(3.14159, precision="0.0001")
        assert result == Decimal("3.1416")

    def test_custom_precision_one_dp(self):
        """Precision '0.1' rounds to one decimal place."""
        assert to_decimal(2.35, precision="0.1") == Decimal("2.4")  # ROUND_HALF_EVEN: 4 is even

    def test_rate_typical_usage(self, five_places):
        """Typical mortgage rate 1.5% converts at rate precision."""
        result = to_decimal(0.015, precision=five_places)
        assert result == Decimal("0.01500")

    def test_rate_very_small_value(self, five_places):
        """A very small insurance rate (0.036%) converts without underflow."""
        result = to_decimal(0.00036, precision=five_places)
        assert result == Decimal("0.00036")

    # -----------------------------------------------------------------------
    # GREEN — boundary values
    # -----------------------------------------------------------------------

    def test_negative_float_converts(self):
        """Negative float (e.g. a delta or correction) converts correctly."""
        assert to_decimal(-0.5) == Decimal("-0.50")

    def test_very_small_float_rounds_to_zero(self):
        """A float smaller than one cent rounds to 0.00."""
        assert to_decimal(0.001) == Decimal("0.00")

    def test_exactly_one_cent(self):
        """0.01 converts to exactly one cent."""
        assert to_decimal(0.01) == Decimal("0.01")

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

    # -----------------------------------------------------------------------
    # Type guard — wrong value types raise TypeError
    # -----------------------------------------------------------------------

    def test_non_numeric_string_raises_type_error(self):
        """A string value raises TypeError with a descriptive message."""
        with pytest.raises(TypeError, match="Expected int or float"):
            to_decimal("abc")  # type: ignore[arg-type]

    def test_none_value_raises_type_error(self):
        """None raises TypeError with a descriptive message."""
        with pytest.raises(TypeError, match="Expected int or float"):
            to_decimal(None)  # type: ignore[arg-type]

    # -----------------------------------------------------------------------
    # Precision validation — invalid precision strings raise ValueError
    # -----------------------------------------------------------------------

    def test_empty_precision_string_raises_value_error(self):
        """An empty precision string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid precision string"):
            to_decimal(1.0, precision="")

    def test_invalid_precision_string_raises_value_error(self):
        """A non-numeric precision string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid precision string"):
            to_decimal(1.0, precision="cents")

    # -----------------------------------------------------------------------
    # Intentional precision loss
    # -----------------------------------------------------------------------

    def test_one_third_float_rounds_to_33_cents(self):
        """1/3 as float rounds to 0.33 — deliberate precision loss at 2 d.p."""
        assert to_decimal(1 / 3) == Decimal("0.33")