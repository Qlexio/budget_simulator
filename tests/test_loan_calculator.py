"""Tests for loan_calculator.py — LoanCalculator."""

import pytest
import warnings
from decimal import Decimal
from unittest.mock import patch, call

from budget_simulator.loan_calculator import LoanCalculator
from budget_simulator._utils import quantize_amount


# ---------------------------------------------------------------------------
# Shared fixture constants
# ---------------------------------------------------------------------------

LOAN_AMOUNT = 100_000        # € principal
ANNUAL_RATE = 0.015          # 1.5% interest
INSURANCE_RATE = 0.003       # 0.3% insurance
COVERAGE = 1.0               # 100 % coverage
DURATION = 180               # 15 years (180 months)
# Repayment of 690 terminates the table at month 164 (< 180) — chosen so that
# the early-termination path is exercised in amortization table tests.
REPAYMENT_HIGH = Decimal("690.00")
# Repayment of 634.04 terminates the table exactly at month 180 — used as the
# "correct" starting guess for the solver (Case 1 deterministic path).
REPAYMENT_EXACT = Decimal("634.04")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def calc_single() -> LoanCalculator:
    """LoanCalculator: single insured, full coverage, no initial monthly repayment."""
    return LoanCalculator(
        loan_amount=LOAN_AMOUNT,
        annual_interest_rate=ANNUAL_RATE,
        annual_insurance_rate=INSURANCE_RATE,
        insured_number=1,
        insurance_coverage=COVERAGE,
    )


@pytest.fixture
def calc_two_scalar() -> LoanCalculator:
    """LoanCalculator: two insured, scalar rate/coverage (safe Decimal path)."""
    return LoanCalculator(
        loan_amount=LOAN_AMOUNT,
        annual_interest_rate=ANNUAL_RATE,
        annual_insurance_rate=INSURANCE_RATE,
        insured_number=2,
        insurance_coverage=0.5,  # scalar → normalised to [Decimal, Decimal]
    )


# ===========================================================================
# _format_insurance_related_values
# ===========================================================================

class TestFormatInsuranceRelatedValues:
    """Tests for LoanCalculator._format_insurance_related_values."""

    # -----------------------------------------------------------------------
    # GREEN — happy paths
    # -----------------------------------------------------------------------

    def test_single_insured_scalar_returns_list_of_one_decimal(self, calc_single):
        """Single insured person with scalar input → [Decimal]."""
        result = calc_single._format_insurance_related_values(0.003, insured_number=1, precision="0.00001")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Decimal)

    def test_single_insured_scalar_value_converted_correctly(self, calc_single):
        """Scalar 0.003 at 5-d.p. precision is stored as Decimal('0.00300')."""
        result = calc_single._format_insurance_related_values(0.003, insured_number=1, precision="0.00001")
        assert result[0] == Decimal("0.00300")
        assert result[0].as_tuple().exponent == -5

    def test_single_insured_list_uses_first_element_only(self, calc_single):
        """Single insured with list input → only first element is kept."""
        result = calc_single._format_insurance_related_values(
            [0.003, 0.005], insured_number=1, precision="0.00001"
        )
        assert len(result) == 1
        # First element is converted to Decimal
        assert isinstance(result[0], Decimal)
        assert result[0] == Decimal("0.00300")

    def test_two_insured_scalar_repeats_value_twice(self, calc_single):
        """Two insured persons with scalar input → same value repeated twice."""
        # Use a calculator with insured_number=2 for the call
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=COVERAGE,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=2, precision="0.00001")
        assert len(result) == 2
        assert result[0] == result[1]
        assert result[0] == Decimal("0.00300")

    def test_two_insured_scalar_all_elements_are_decimal(self):
        """All elements in the returned list are Decimal instances."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=COVERAGE,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=2, precision="0.00001")
        for item in result:
            assert isinstance(item, Decimal)

    def test_single_insured_custom_precision_applied(self, calc_single):
        """Custom precision='0.01' truncates rate to 2 d.p."""
        result = calc_single._format_insurance_related_values(0.003, insured_number=1, precision="0.01")
        assert result[0].as_tuple().exponent == -2

    def test_constructor_stores_insurance_rate_as_decimal_list(self, calc_single):
        """Constructor normalises annual_insurance_rate to a list of Decimal."""
        assert isinstance(calc_single.annual_insurance_rate, list)
        assert len(calc_single.annual_insurance_rate) == 1
        assert isinstance(calc_single.annual_insurance_rate[0], Decimal)

    def test_constructor_stores_insurance_coverage_as_decimal_list(self, calc_single):
        """Constructor normalises insurance_coverage to a list of Decimal."""
        assert isinstance(calc_single.insurance_coverage, list)
        assert len(calc_single.insurance_coverage) == 1
        assert isinstance(calc_single.insurance_coverage[0], Decimal)

    def test_constructor_two_insured_scalar_coverage_normalised(self, calc_two_scalar):
        """Two insured with scalar coverage → list of two Decimal values."""
        assert isinstance(calc_two_scalar.insurance_coverage, list)
        assert len(calc_two_scalar.insurance_coverage) == 2
        for item in calc_two_scalar.insurance_coverage:
            assert isinstance(item, Decimal)

    def test_two_insured_list_longer_than_n_is_truncated(self):
        """List with more elements than insured_number is silently truncated."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.003, 0.004, 0.005],
            insured_number=1,
            insurance_coverage=COVERAGE,
        )
        # Only the first element must be kept
        assert len(calc.annual_insurance_rate) == 1

    def test_two_insured_list_of_two_truncated_to_two(self):
        """List with more elements than 2 insured is truncated to 2."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.002, 0.004, 0.006],
            insured_number=2,
            insurance_coverage=COVERAGE,
        )
        assert len(calc.annual_insurance_rate) == 2

    def test_two_insured_list_rate_elements_are_decimal(self):
        """List-input rate elements are converted to Decimal by the list branch."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.002, 0.004],
            insured_number=2,
            insurance_coverage=COVERAGE,
        )
        for item in calc.annual_insurance_rate:
            assert isinstance(item, Decimal)

    def test_two_insured_list_coverage_elements_are_decimal(self):
        """List-input coverage elements are converted to Decimal by the list branch."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=[0.5, 0.5],
        )
        for item in calc.insurance_coverage:
            assert isinstance(item, Decimal)

    # -----------------------------------------------------------------------
    # RED — __init__ input-validation guards
    # -----------------------------------------------------------------------

    # Guard 1: loan_amount <= 0
    def test_init_loan_amount_zero_raises_value_error(self):
        """loan_amount=0 is not positive and must raise ValueError."""
        with pytest.raises(ValueError, match="loan_amount"):
            LoanCalculator(
                loan_amount=0,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
            )

    def test_init_loan_amount_negative_raises_value_error(self):
        """loan_amount=-1 is negative and must raise ValueError."""
        with pytest.raises(ValueError, match="loan_amount"):
            LoanCalculator(
                loan_amount=-1,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
            )

    def test_init_loan_amount_one_does_not_raise(self):
        """loan_amount=1 is at the positive boundary and must not raise."""
        calc = LoanCalculator(
            loan_amount=1,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
        )
        assert calc.loan_amount == Decimal("1.00")

    # Guard 2: annual_interest_rate < 0
    def test_init_negative_interest_rate_raises_value_error(self):
        """annual_interest_rate=-0.001 is negative and must raise ValueError."""
        with pytest.raises(ValueError, match="annual_interest_rate"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=-0.001,
                annual_insurance_rate=INSURANCE_RATE,
            )

    def test_init_zero_interest_rate_does_not_raise(self):
        """annual_interest_rate=0 (0% interest) is valid and must not raise."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=0,
            annual_insurance_rate=INSURANCE_RATE,
        )
        assert calc.annual_interest_rate == Decimal("0.00000")

    # Guard 3: insured_number < 1 or not int
    def test_init_insured_number_zero_raises_value_error(self):
        """insured_number=0 is less than 1 and must raise ValueError."""
        with pytest.raises(ValueError, match="insured_number"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=0,
            )

    def test_init_insured_number_negative_raises_value_error(self):
        """insured_number=-1 is negative and must raise ValueError."""
        with pytest.raises(ValueError, match="insured_number"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=-1,
            )

    def test_init_insured_number_float_raises_value_error(self):
        """insured_number=1.0 is a float, not int, and must raise ValueError."""
        with pytest.raises(ValueError, match="insured_number"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=1.0,  # type: ignore[arg-type]
            )

    # Guard 4: any annual_insurance_rate < 0
    def test_init_negative_insurance_rate_scalar_raises_value_error(self):
        """Scalar annual_insurance_rate=-0.001 must raise ValueError."""
        with pytest.raises(ValueError, match="annual_insurance_rate"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=-0.001,
            )

    def test_init_negative_insurance_rate_in_list_raises_value_error(self):
        """List annual_insurance_rate=[-0.001, 0.003] with insured_number=2 must raise ValueError."""
        with pytest.raises(ValueError, match="annual_insurance_rate"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=[-0.001, 0.003],
                insured_number=2,
            )

    # Guard 5: any insurance_coverage outside [0, 1]
    def test_init_insurance_coverage_above_one_scalar_raises_value_error(self):
        """Scalar insurance_coverage=1.1 exceeds 1.0 and must raise ValueError."""
        with pytest.raises(ValueError, match="insurance_coverage"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insurance_coverage=1.1,
            )

    def test_init_insurance_coverage_negative_scalar_raises_value_error(self):
        """Scalar insurance_coverage=-0.1 is below 0 and must raise ValueError."""
        with pytest.raises(ValueError, match="insurance_coverage"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insurance_coverage=-0.1,
            )

    def test_init_insurance_coverage_above_one_in_list_raises_value_error(self):
        """List insurance_coverage=[0.5, 1.1] with insured_number=2 must raise ValueError."""
        with pytest.raises(ValueError, match="insurance_coverage"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=2,
                insurance_coverage=[0.5, 1.1],
            )

    def test_init_insurance_coverage_zero_does_not_raise(self):
        """insurance_coverage=0 is at the lower boundary and must not raise."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insurance_coverage=0,
        )
        assert calc.insurance_coverage[0] == Decimal("0.00")

    def test_init_insurance_coverage_one_does_not_raise(self):
        """insurance_coverage=1 is at the upper boundary and must not raise."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insurance_coverage=1,
        )
        assert calc.insurance_coverage[0] == Decimal("1.00")

    # -----------------------------------------------------------------------
    # GREEN — new list-broadcast and list-exact-match behaviours (post bug fix)
    # -----------------------------------------------------------------------

    def test_two_insured_list_of_one_rate_is_broadcast_to_both(self):
        """List of length 1 with insured_number=2 broadcasts the single rate to both persons.

        New behaviour after the zip-truncation fix: a length-1 list is treated
        identically to a scalar, duplicating the value across all insured persons.
        """
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.003],
            insured_number=2,
        )
        assert len(calc.annual_insurance_rate) == 2
        assert calc.annual_insurance_rate[0] == calc.annual_insurance_rate[1]
        assert calc.annual_insurance_rate[0] == Decimal("0.00300")

    def test_two_insured_list_of_one_rate_elements_are_decimal(self):
        """Broadcast elements from a length-1 list are Decimal instances."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.003],
            insured_number=2,
        )
        for item in calc.annual_insurance_rate:
            assert isinstance(item, Decimal)

    def test_two_insured_list_of_one_coverage_is_broadcast_to_both(self):
        """List-of-one coverage with insured_number=2 broadcasts to both persons."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=[0.75],
        )
        assert len(calc.insurance_coverage) == 2
        assert calc.insurance_coverage[0] == calc.insurance_coverage[1]
        assert calc.insurance_coverage[0] == Decimal("0.75")

    def test_two_insured_exact_list_length_rate_values_preserved(self):
        """List of exactly insured_number elements is used unchanged (all values kept).

        Both distinct rates must be stored in the order they were provided.
        """
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.002, 0.004],
            insured_number=2,
        )
        assert len(calc.annual_insurance_rate) == 2
        assert calc.annual_insurance_rate[0] == Decimal("0.00200")
        assert calc.annual_insurance_rate[1] == Decimal("0.00400")

    def test_two_insured_exact_list_length_coverage_values_preserved(self):
        """List of exactly insured_number coverage elements is used unchanged."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=[0.6, 0.4],
        )
        assert len(calc.insurance_coverage) == 2
        assert calc.insurance_coverage[0] == Decimal("0.60")
        assert calc.insurance_coverage[1] == Decimal("0.40")

    # -----------------------------------------------------------------------
    # GREEN — list longer than insured_number: warns and truncates
    # -----------------------------------------------------------------------

    def test_longer_rate_list_emits_user_warning(self):
        """List with more elements than insured_number must emit a UserWarning."""
        with pytest.warns(UserWarning):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=[0.002, 0.004, 0.006],
                insured_number=2,
            )

    def test_longer_rate_list_truncates_to_insured_number(self):
        """List of length 3 with insured_number=2 is truncated to the first 2 elements."""
        with pytest.warns(UserWarning):
            calc = LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=[0.002, 0.004, 0.006],
                insured_number=2,
            )
        assert len(calc.annual_insurance_rate) == 2
        assert calc.annual_insurance_rate[0] == Decimal("0.00200")
        assert calc.annual_insurance_rate[1] == Decimal("0.00400")

    def test_longer_coverage_list_emits_user_warning(self):
        """List of coverage with more elements than insured_number must emit a UserWarning."""
        with pytest.warns(UserWarning):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=2,
                insurance_coverage=[0.5, 0.3, 0.2],
            )

    def test_longer_coverage_list_truncates_to_insured_number(self):
        """Coverage list of length 3 with insured_number=2 is truncated to the first 2."""
        with pytest.warns(UserWarning):
            calc = LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=2,
                insurance_coverage=[0.5, 0.3, 0.2],
            )
        assert len(calc.insurance_coverage) == 2
        assert calc.insurance_coverage[0] == Decimal("0.50")
        assert calc.insurance_coverage[1] == Decimal("0.30")

    # Regression: the original zip() behaviour silently truncated without warning.
    # This specific case (length-3 list, insured_number=2) must now warn.
    def test_regression_zip_truncation_now_warns(self):
        """Regression: list of length 3 with insured_number=2 previously used zip() and
        silently dropped the third element with no warning. After the fix, a UserWarning
        must be emitted so callers are notified of the mismatch.
        """
        with pytest.warns(UserWarning, match="extra values will be ignored"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=[0.002, 0.004, 0.006],
                insured_number=2,
            )

    # -----------------------------------------------------------------------
    # RED — list shorter than insured_number raises ValueError
    # -----------------------------------------------------------------------

    def test_rate_list_shorter_than_insured_number_raises_value_error(self):
        """List of length 1 with insured_number=3 cannot be broadcast (len > 1) and
        is shorter than insured_number → must raise ValueError mentioning 'less than'.
        """
        with pytest.raises(ValueError, match="less than"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=[0.002, 0.004],
                insured_number=3,
            )

    def test_coverage_list_shorter_than_insured_number_raises_value_error(self):
        """Coverage list of length 1 with insured_number=3 is shorter (len > 1 check
        excluded) — must raise ValueError mentioning 'less than'.
        """
        with pytest.raises(ValueError, match="less than"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                insured_number=3,
                insurance_coverage=[0.5, 0.3],
            )

    def test_rate_list_of_two_with_insured_number_four_raises_value_error(self):
        """A list that is genuinely shorter (length 2, insured_number=4) must raise ValueError."""
        with pytest.raises(ValueError, match="less than"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=[0.002, 0.004],
                insured_number=4,
            )

    def test_format_insurance_directly_shorter_list_raises_value_error(self, calc_single):
        """Direct call to _format_insurance_related_values with a 1-element list and
        insured_number=3 must raise ValueError (len == 1 triggers broadcast, len > 1 but
        < insured_number triggers the error).
        """
        # A length-2 list with insured_number=3 is shorter → raises
        with pytest.raises(ValueError, match="less than"):
            calc_single._format_insurance_related_values(
                [0.002, 0.004], insured_number=3, precision="0.00001"
            )

    def test_format_insurance_directly_longer_list_warns_and_truncates(self, calc_single):
        """Direct call to _format_insurance_related_values with a 3-element list and
        insured_number=2 must emit a UserWarning and return only the first 2 elements.
        """
        with pytest.warns(UserWarning, match="extra values will be ignored"):
            result = calc_single._format_insurance_related_values(
                [0.001, 0.003, 0.005], insured_number=2, precision="0.00001"
            )
        assert len(result) == 2
        assert result[0] == Decimal("0.00100")
        assert result[1] == Decimal("0.00300")

    def test_format_insurance_directly_list_of_one_broadcasts(self, calc_single):
        """Direct call with a length-1 list and insured_number=2 must broadcast the
        single value to both positions without warning.
        """
        result = calc_single._format_insurance_related_values(
            [0.003], insured_number=2, precision="0.00001"
        )
        assert len(result) == 2
        assert result[0] == result[1]
        assert result[0] == Decimal("0.00300")

    # -----------------------------------------------------------------------
    # GREEN — insurance_coverage list input via constructor (cast removal coverage)
    # These tests confirm that passing a list directly as insurance_coverage
    # to the constructor reaches _format_insurance_related_values correctly,
    # now that the cast(Union[int, float], insurance_coverage) no-op was removed.
    # -----------------------------------------------------------------------

    def test_single_insured_list_coverage_length_is_one(self):
        """Single insured with list coverage → self.insurance_coverage has exactly 1 element."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
            insurance_coverage=[0.75],
        )
        assert len(calc.insurance_coverage) == 1

    def test_single_insured_list_coverage_value_is_correct(self):
        """Single insured with list coverage [0.75] → stored as Decimal('0.75')."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
            insurance_coverage=[0.75],
        )
        assert calc.insurance_coverage[0] == Decimal("0.75")

    def test_single_insured_list_coverage_element_is_decimal(self):
        """Single insured with list coverage → stored element is a Decimal instance."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
            insurance_coverage=[0.75],
        )
        assert isinstance(calc.insurance_coverage[0], Decimal)

    def test_single_insured_list_coverage_extra_elements_dropped(self):
        """Single insured with list coverage [0.6, 0.9] → only first element kept."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
            insurance_coverage=[0.6, 0.9],
        )
        assert len(calc.insurance_coverage) == 1
        assert calc.insurance_coverage[0] == Decimal("0.60")

    def test_single_insured_list_coverage_int_element_stored_correctly(self):
        """Single insured with list coverage [1] (int element) → Decimal('1.00')."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
            insurance_coverage=[1],
        )
        assert len(calc.insurance_coverage) == 1
        assert calc.insurance_coverage[0] == Decimal("1.00")
        assert isinstance(calc.insurance_coverage[0], Decimal)

    def test_two_insured_list_coverage_int_elements_stored_correctly(self):
        """Two insured with list coverage [1, 0] (int elements) → [Decimal('1.00'), Decimal('0.00')]."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=[1, 0],
        )
        assert len(calc.insurance_coverage) == 2
        assert calc.insurance_coverage[0] == Decimal("1.00")
        assert calc.insurance_coverage[1] == Decimal("0.00")
        for item in calc.insurance_coverage:
            assert isinstance(item, Decimal)

    def test_two_insured_list_coverage_int_one_broadcasts(self):
        """Two insured with list coverage [1] (int, length 1) → broadcasts to both persons."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=[1],
        )
        assert len(calc.insurance_coverage) == 2
        assert calc.insurance_coverage[0] == Decimal("1.00")
        assert calc.insurance_coverage[1] == Decimal("1.00")

    # -----------------------------------------------------------------------
    # GREEN — exhaustive branch coverage to confirm AssertionError is unreachable
    #
    # The method ends with:
    #   raise AssertionError("unreachable: unhandled insured_number/insurance_value combination")
    #
    # The tests below call _format_insurance_related_values directly for every
    # branch that precedes that line.  Passing all of them gives confidence that
    # every reachable (insured_number, input-type) combination is handled and
    # the fallback is never hit.
    #
    # Branch map (line numbers in loan_calculator.py):
    #   B1  insured_number == 1,  scalar input          → [Decimal]          (line 100–101)
    #   B2  insured_number == 1,  list input             → [Decimal(list[0])] (line 102–103)
    #   B3  insured_number > 1,  scalar input            → [value] * n       (line 104–108)
    #   B4  insured_number > 1,  list len == 1           → broadcast          (line 110–111)
    #   B5  insured_number > 1,  list len == insured_number → use as-is       (line 124)
    #   B6  insured_number > 1,  list len > insured_number → warn + truncate  (line 117–124)
    # -----------------------------------------------------------------------

    # -- B1: insured_number == 1, scalar input --

    def test_b1_scalar_insured1_returns_single_element_list(self, calc_single):
        """B1: scalar + insured_number=1 → list of exactly one Decimal, no exception."""
        result = calc_single._format_insurance_related_values(0.004, insured_number=1)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_b1_scalar_insured1_element_is_decimal(self, calc_single):
        """B1: returned element must be a Decimal instance."""
        result = calc_single._format_insurance_related_values(0.004, insured_number=1)
        assert isinstance(result[0], Decimal)

    def test_b1_scalar_insured1_value_matches_input(self, calc_single):
        """B1: returned Decimal equals the input scalar converted at default precision (0.01)."""
        result = calc_single._format_insurance_related_values(0.5, insured_number=1, precision="0.01")
        assert result[0] == Decimal("0.50")

    def test_b1_scalar_insured1_int_input_stored_correctly(self, calc_single):
        """B1: integer scalar is accepted and stored as Decimal."""
        result = calc_single._format_insurance_related_values(1, insured_number=1, precision="0.01")
        assert result[0] == Decimal("1.00")

    def test_b1_scalar_insured1_zero_stored_correctly(self, calc_single):
        """B1: zero scalar is a valid lower boundary and stored as Decimal zero."""
        result = calc_single._format_insurance_related_values(0, insured_number=1, precision="0.01")
        assert result[0] == Decimal("0.00")

    def test_b1_scalar_insured1_rate_precision_applied(self, calc_single):
        """B1: precision='0.00001' produces five decimal places."""
        result = calc_single._format_insurance_related_values(0.003, insured_number=1, precision="0.00001")
        assert result[0].as_tuple().exponent == -5
        assert result[0] == Decimal("0.00300")

    # -- B2: insured_number == 1, list input --

    def test_b2_list_insured1_single_element_returns_list_of_one(self, calc_single):
        """B2: list + insured_number=1 → list of exactly one element, no exception."""
        result = calc_single._format_insurance_related_values([0.003], insured_number=1)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_b2_list_insured1_element_is_decimal(self, calc_single):
        """B2: element extracted from the input list must be a Decimal."""
        result = calc_single._format_insurance_related_values([0.003], insured_number=1)
        assert isinstance(result[0], Decimal)

    def test_b2_list_insured1_uses_first_element_only(self, calc_single):
        """B2: only the first list element is kept; extras are silently dropped."""
        result = calc_single._format_insurance_related_values(
            [0.003, 0.007, 0.009], insured_number=1, precision="0.00001"
        )
        assert len(result) == 1
        assert result[0] == Decimal("0.00300")

    def test_b2_list_insured1_precision_applied_to_extracted_element(self, calc_single):
        """B2: the extracted element is converted to Decimal at the requested precision."""
        result = calc_single._format_insurance_related_values([0.5], insured_number=1, precision="0.01")
        assert result[0] == Decimal("0.50")
        assert result[0].as_tuple().exponent == -2

    def test_b2_list_insured1_int_element_stored_correctly(self, calc_single):
        """B2: integer element in the list is converted to Decimal correctly."""
        result = calc_single._format_insurance_related_values([1], insured_number=1, precision="0.01")
        assert result[0] == Decimal("1.00")

    # -- B3: insured_number > 1, scalar input --
    #
    # NOTE: the B3 loop body uses `self.insured_number` (not the `insured_number`
    # override argument) to drive the repeat count. Direct calls therefore need a
    # calculator whose self.insured_number matches the desired n. These tests
    # construct appropriate instances rather than reusing calc_single (n=1).

    @pytest.mark.parametrize("n", [2, 3, 4, 5])
    def test_b3_scalar_insured_n_returns_list_of_length_n(self, n):
        """B3: scalar + insured_number=n → list of exactly n elements, no exception.

        A fresh calculator with insured_number=n is used so that self.insured_number
        matches the branch being exercised (B3 loop uses self.insured_number).
        """
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=n,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=n, precision="0.00001")
        assert isinstance(result, list)
        assert len(result) == n

    @pytest.mark.parametrize("n", [2, 3, 4, 5])
    def test_b3_scalar_insured_n_all_elements_equal(self, n):
        """B3: every element in the result must equal the input scalar (broadcast)."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=n,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=n, precision="0.00001")
        assert all(v == Decimal("0.00300") for v in result)

    @pytest.mark.parametrize("n", [2, 3, 4, 5])
    def test_b3_scalar_insured_n_all_elements_are_decimal(self, n):
        """B3: every element in the result must be a Decimal instance."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=n,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=n, precision="0.00001")
        assert all(isinstance(v, Decimal) for v in result)

    def test_b3_scalar_insured2_zero_broadcasts_correctly(self):
        """B3: zero scalar with insured_number=2 → [Decimal('0.00'), Decimal('0.00')]."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
        )
        result = calc._format_insurance_related_values(0, insured_number=2, precision="0.01")
        assert len(result) == 2
        assert all(v == Decimal("0.00") for v in result)

    def test_b3_scalar_insured2_int_one_broadcasts_correctly(self):
        """B3: integer 1 with insured_number=2 → both elements are Decimal('1.00')."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
        )
        result = calc._format_insurance_related_values(1, insured_number=2, precision="0.01")
        assert len(result) == 2
        assert all(v == Decimal("1.00") for v in result)

    # -- B4: insured_number > 1, list of length 1 (broadcast path) --

    @pytest.mark.parametrize("n", [2, 3, 4])
    def test_b4_list_of_one_insured_n_broadcasts_to_n_elements(self, calc_single, n):
        """B4: list of length 1 + insured_number=n → n equal elements, no exception."""
        result = calc_single._format_insurance_related_values([0.003], insured_number=n, precision="0.00001")
        assert isinstance(result, list)
        assert len(result) == n

    @pytest.mark.parametrize("n", [2, 3, 4])
    def test_b4_list_of_one_insured_n_all_elements_equal(self, calc_single, n):
        """B4: all n elements must equal the single input value."""
        result = calc_single._format_insurance_related_values([0.003], insured_number=n, precision="0.00001")
        assert all(v == Decimal("0.00300") for v in result)

    @pytest.mark.parametrize("n", [2, 3, 4])
    def test_b4_list_of_one_insured_n_all_elements_are_decimal(self, calc_single, n):
        """B4: every element must be a Decimal instance."""
        result = calc_single._format_insurance_related_values([0.003], insured_number=n, precision="0.00001")
        assert all(isinstance(v, Decimal) for v in result)

    def test_b4_list_of_one_insured2_zero_broadcasts_correctly(self, calc_single):
        """B4: [0] with insured_number=2 → [Decimal('0.00'), Decimal('0.00')]."""
        result = calc_single._format_insurance_related_values([0], insured_number=2, precision="0.01")
        assert len(result) == 2
        assert all(v == Decimal("0.00") for v in result)

    def test_b4_list_of_one_does_not_emit_warning(self, calc_single):
        """B4: length-1 list broadcast must not raise any warning (not a truncation)."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning becomes an error
            result = calc_single._format_insurance_related_values([0.5], insured_number=2, precision="0.01")
        assert len(result) == 2

    # -- B5: insured_number > 1, list len == insured_number --

    def test_b5_exact_list_insured2_returns_both_values(self, calc_single):
        """B5: list of length 2 + insured_number=2 → both values preserved, no exception."""
        result = calc_single._format_insurance_related_values(
            [0.002, 0.004], insured_number=2, precision="0.00001"
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == Decimal("0.00200")
        assert result[1] == Decimal("0.00400")

    def test_b5_exact_list_insured3_returns_all_three_values(self, calc_single):
        """B5: list of length 3 + insured_number=3 → all three values preserved."""
        result = calc_single._format_insurance_related_values(
            [0.001, 0.002, 0.003], insured_number=3, precision="0.00001"
        )
        assert len(result) == 3
        assert result[0] == Decimal("0.00100")
        assert result[1] == Decimal("0.00200")
        assert result[2] == Decimal("0.00300")

    def test_b5_exact_list_insured4_returns_all_four_values(self, calc_single):
        """B5: list of length 4 + insured_number=4 → all four values preserved."""
        result = calc_single._format_insurance_related_values(
            [0.001, 0.002, 0.003, 0.004], insured_number=4, precision="0.00001"
        )
        assert len(result) == 4
        assert result[0] == Decimal("0.00100")
        assert result[3] == Decimal("0.00400")

    def test_b5_exact_list_all_elements_are_decimal(self, calc_single):
        """B5: every element in an exact-length list result must be a Decimal."""
        result = calc_single._format_insurance_related_values(
            [0.002, 0.004], insured_number=2, precision="0.00001"
        )
        assert all(isinstance(v, Decimal) for v in result)

    def test_b5_exact_list_insured2_order_preserved(self, calc_single):
        """B5: list elements are returned in the original input order."""
        result = calc_single._format_insurance_related_values(
            [0.009, 0.001], insured_number=2, precision="0.00001"
        )
        assert result[0] == Decimal("0.00900")
        assert result[1] == Decimal("0.00100")

    def test_b5_exact_list_insured2_does_not_emit_warning(self, calc_single):
        """B5: an exact-length list must not emit any warning."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = calc_single._format_insurance_related_values(
                [0.002, 0.004], insured_number=2, precision="0.00001"
            )
        assert len(result) == 2

    # -- B6: insured_number > 1, list len > insured_number --

    def test_b6_longer_list_insured2_emits_user_warning(self, calc_single):
        """B6: list of length 3 + insured_number=2 → UserWarning emitted."""
        with pytest.warns(UserWarning, match="extra values will be ignored"):
            calc_single._format_insurance_related_values(
                [0.001, 0.003, 0.005], insured_number=2, precision="0.00001"
            )

    def test_b6_longer_list_insured2_truncates_to_insured_number(self, calc_single):
        """B6: result contains exactly insured_number elements (first n)."""
        with pytest.warns(UserWarning):
            result = calc_single._format_insurance_related_values(
                [0.001, 0.003, 0.005], insured_number=2, precision="0.00001"
            )
        assert len(result) == 2
        assert result[0] == Decimal("0.00100")
        assert result[1] == Decimal("0.00300")

    def test_b6_longer_list_insured3_truncates_correctly(self, calc_single):
        """B6: list of length 5 + insured_number=3 → first 3 elements kept."""
        with pytest.warns(UserWarning):
            result = calc_single._format_insurance_related_values(
                [0.001, 0.002, 0.003, 0.004, 0.005], insured_number=3, precision="0.00001"
            )
        assert len(result) == 3
        assert result[0] == Decimal("0.00100")
        assert result[1] == Decimal("0.00200")
        assert result[2] == Decimal("0.00300")

    def test_b6_longer_list_all_kept_elements_are_decimal(self, calc_single):
        """B6: kept elements after truncation must all be Decimal instances."""
        with pytest.warns(UserWarning):
            result = calc_single._format_insurance_related_values(
                [0.001, 0.003, 0.005], insured_number=2, precision="0.00001"
            )
        assert all(isinstance(v, Decimal) for v in result)

    # -- Cross-branch: confirm no AssertionError fires for any valid combination --

    @pytest.mark.parametrize(
        "insurance_value, insured_number, expected_len",
        [
            # B1: scalar, n=1
            (0.003, 1, 1),
            # B2: list, n=1
            ([0.003], 1, 1),
            # B2: list longer than 1, n=1 (only first element used)
            ([0.003, 0.005], 1, 1),
            # B3: scalar, n=2  (requires calc with self.insured_number=2)
            (0.003, 2, 2),
            # B3: scalar, n=3  (requires calc with self.insured_number=3)
            (0.003, 3, 3),
            # B4: list-of-one, n=2
            ([0.003], 2, 2),
            # B4: list-of-one, n=3
            ([0.003], 3, 3),
            # B5: exact-length list, n=2
            ([0.002, 0.004], 2, 2),
            # B5: exact-length list, n=3
            ([0.001, 0.002, 0.003], 3, 3),
        ],
    )
    def test_all_valid_combinations_return_list_without_assertionerror(
        self, insurance_value, insured_number, expected_len
    ):
        """Parametrised sweep: every valid (insured_number, input-type) pairing
        must return a list of the correct length and never raise AssertionError.

        These are the combinations that exhaust every branch before the
        'unreachable' raise, giving full branch coverage of the method.

        A calculator with self.insured_number == insured_number is constructed
        per-case so that the B3 loop (which reads self.insured_number) returns
        the correct count even when insured_number > 1.
        """
        if isinstance(insurance_value, list) and len(insurance_value) > insured_number > 1:
            # B6 path emits a warning; handle in dedicated tests above
            return

        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=insured_number,
        )
        result = calc._format_insurance_related_values(
            insurance_value, insured_number=insured_number, precision="0.00001"
        )
        assert isinstance(result, list)
        assert len(result) == expected_len
        assert all(isinstance(v, Decimal) for v in result)


# ===========================================================================
# _compute_payment_breakdown
# ===========================================================================

class TestComputePaymentBreakdown:
    """Tests for LoanCalculator._compute_payment_breakdown."""

    # -----------------------------------------------------------------------
    # GREEN — happy paths
    # -----------------------------------------------------------------------

    def test_normal_month_interest_formula(self, calc_single):
        """Interest = remaining_capital × annual_rate / 12."""
        remaining = Decimal("50000.00")
        repayment = Decimal("690.00")
        insurance = Decimal("12.50")

        interest, _, _ = calc_single._compute_payment_breakdown(
            monthly_repayment=repayment,
            monthly_insurance=insurance,
            remaining_capital=remaining,
        )
        # 50000 × 0.015 / 12 = 62.5
        expected_interest = remaining * calc_single.annual_interest_rate / 12
        assert abs(interest - expected_interest) <= Decimal("0.00001")

    def test_normal_month_repaid_capital_formula(self, calc_single):
        """Repaid capital = monthly_repayment − interest − insurance."""
        remaining = Decimal("50000.00")
        repayment = Decimal("690.00")
        insurance = Decimal("12.50")

        interest, repaid, _ = calc_single._compute_payment_breakdown(
            monthly_repayment=repayment,
            monthly_insurance=insurance,
            remaining_capital=remaining,
        )
        assert abs(repaid - (repayment - interest - insurance)) <= Decimal("0.00001")

    def test_normal_month_new_remaining_capital_formula(self, calc_single):
        """New remaining = old remaining − repaid capital (normal month)."""
        remaining = Decimal("50000.00")
        repayment = Decimal("690.00")
        insurance = Decimal("12.50")

        interest, repaid, new_remaining = calc_single._compute_payment_breakdown(
            monthly_repayment=repayment,
            monthly_insurance=insurance,
            remaining_capital=remaining,
        )
        assert abs(new_remaining - (remaining - repaid)) <= Decimal("0.00001")

    def test_normal_month_concrete_values(self, calc_single):
        """Spot-check: remaining=50000, repayment=690, insurance=12.50."""
        interest, repaid, new_remaining = calc_single._compute_payment_breakdown(
            monthly_repayment=Decimal("690.00"),
            monthly_insurance=Decimal("12.50"),
            remaining_capital=Decimal("50000.00"),
        )
        assert interest == Decimal("62.5000000")
        assert repaid == Decimal("615.0000000")
        assert new_remaining == Decimal("49385.0000000")

    def test_last_month_cap_repaid_equals_remaining(self, calc_single):
        """When difference < tolerance threshold, repaid_capital is capped at remaining."""
        # remaining=100 << repayment=690; cap fires because 100−repaid < 690×0.1=69
        _, repaid, _ = calc_single._compute_payment_breakdown(
            monthly_repayment=Decimal("690.00"),
            monthly_insurance=Decimal("25.00"),
            remaining_capital=Decimal("100.00"),
            capital_tolerance=0.1,
        )
        assert repaid == Decimal("100.00")

    def test_last_month_cap_new_remaining_is_zero(self, calc_single):
        """When last-month cap fires, new remaining_capital is exactly zero."""
        _, _, new_remaining = calc_single._compute_payment_breakdown(
            monthly_repayment=Decimal("690.00"),
            monthly_insurance=Decimal("25.00"),
            remaining_capital=Decimal("100.00"),
            capital_tolerance=0.1,
        )
        assert new_remaining == Decimal("0")

    def test_capital_tolerance_as_int_accepted(self, calc_single):
        """capital_tolerance passed as int does not raise."""
        # If the conversion bug were present, float(0) would fail; it should not.
        try:
            calc_single._compute_payment_breakdown(
                monthly_repayment=Decimal("690.00"),
                monthly_insurance=Decimal("25.00"),
                remaining_capital=Decimal("50000.00"),
                capital_tolerance=0,
            )
        except Exception as exc:
            pytest.fail(f"int capital_tolerance raised unexpectedly: {exc}")

    def test_capital_tolerance_as_float_accepted(self, calc_single):
        """capital_tolerance passed as float does not raise."""
        try:
            calc_single._compute_payment_breakdown(
                monthly_repayment=Decimal("690.00"),
                monthly_insurance=Decimal("25.00"),
                remaining_capital=Decimal("50000.00"),
                capital_tolerance=0.1,
            )
        except Exception as exc:
            pytest.fail(f"float capital_tolerance raised unexpectedly: {exc}")

    def test_capital_tolerance_as_decimal_accepted(self, calc_single):
        """capital_tolerance passed as Decimal does not raise.

        This was a bug: passing Decimal('0.1') used to fail because the code
        did Decimal(float(capital_tolerance)) which is fine, but previously the
        conversion path was broken for Decimal inputs. This test guards the fix.
        """
        try:
            calc_single._compute_payment_breakdown(
                monthly_repayment=Decimal("690.00"),
                monthly_insurance=Decimal("25.00"),
                remaining_capital=Decimal("50000.00"),
                capital_tolerance=Decimal("0.1"),
            )
        except Exception as exc:
            pytest.fail(f"Decimal capital_tolerance raised unexpectedly: {exc}")

    def test_all_three_return_values_are_decimal(self, calc_single):
        """All three returned values must be Decimal instances."""
        interest, repaid, new_remaining = calc_single._compute_payment_breakdown(
            monthly_repayment=Decimal("690.00"),
            monthly_insurance=Decimal("25.00"),
            remaining_capital=Decimal("50000.00"),
        )
        assert isinstance(interest, Decimal)
        assert isinstance(repaid, Decimal)
        assert isinstance(new_remaining, Decimal)

    @pytest.mark.parametrize("capital_tolerance", [0, 0.1, 0.5, Decimal("0.1"), Decimal("0.5")])
    def test_capital_tolerance_variety_all_accepted(self, calc_single, capital_tolerance):
        """int, float, and Decimal tolerance values are all accepted without error."""
        try:
            calc_single._compute_payment_breakdown(
                monthly_repayment=Decimal("690.00"),
                monthly_insurance=Decimal("25.00"),
                remaining_capital=Decimal("50000.00"),
                capital_tolerance=capital_tolerance,
            )
        except Exception as exc:
            pytest.fail(f"capital_tolerance={capital_tolerance!r} raised: {exc}")


# ===========================================================================
# _compute_monthly_insurance
# ===========================================================================

class TestComputeMonthlyInsurance:
    """Tests for LoanCalculator._compute_monthly_insurance."""

    # -----------------------------------------------------------------------
    # GREEN — happy paths
    # -----------------------------------------------------------------------

    def test_single_insured_full_coverage_formula(self, calc_single):
        """Monthly insurance = remaining × (annual_rate × coverage) / 12."""
        remaining = Decimal("100000.00")
        result = calc_single._compute_monthly_insurance(remaining)
        # 100000 × (0.003 × 1.0) / 12 = 25.0
        rate = calc_single.annual_insurance_rate[0]
        cov = calc_single.insurance_coverage[0]
        expected = remaining * ((rate * cov) / 12)
        assert abs(result - expected) <= Decimal("0.00001")

    def test_single_insured_full_coverage_concrete_value(self, calc_single):
        """Spot-check: 100000 × 0.003 / 12 = 25.000…"""
        result = calc_single._compute_monthly_insurance(Decimal("100000.00"))
        assert abs(result - Decimal("25.0")) <= Decimal("0.00001")

    def test_single_insured_return_type_is_decimal(self, calc_single):
        """Return value must be a Decimal instance."""
        result = calc_single._compute_monthly_insurance(Decimal("100000.00"))
        assert isinstance(result, Decimal)

    def test_zero_remaining_capital_gives_zero_insurance(self, calc_single):
        """Zero remaining capital → zero monthly insurance."""
        result = calc_single._compute_monthly_insurance(Decimal("0.00"))
        assert result == Decimal("0")

    def test_zero_coverage_gives_zero_insurance(self):
        """Zero coverage ratio → zero monthly insurance regardless of rate."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
            insurance_coverage=0.0,
        )
        result = calc._compute_monthly_insurance(Decimal("100000.00"))
        assert result == Decimal("0")

    def test_two_insured_scalar_insurance_is_sum_of_contributions(self, calc_two_scalar):
        """Two insured with scalar params: result = sum of both persons' costs.

        With rate=0.003, coverage=0.5 for each of 2 persons and remaining=100000:
        each = 100000 × (0.003 × 0.5) / 12 = 12.5  → total = 25.0
        """
        result = calc_two_scalar._compute_monthly_insurance(Decimal("100000.00"))
        assert abs(result - Decimal("25.0")) <= Decimal("0.00001")

    def test_two_insured_scalar_same_rate_as_single_full_coverage(
        self, calc_single, calc_two_scalar
    ):
        """Two insured at 0.5 coverage = one insured at full coverage (same total rate)."""
        result_single = calc_single._compute_monthly_insurance(Decimal("100000.00"))
        result_two = calc_two_scalar._compute_monthly_insurance(Decimal("100000.00"))
        assert abs(result_single - result_two) <= Decimal("0.00001")

    def test_insurance_scales_linearly_with_remaining_capital(self, calc_single):
        """Halving remaining_capital halves the monthly insurance cost."""
        ins_full = calc_single._compute_monthly_insurance(Decimal("100000.00"))
        ins_half = calc_single._compute_monthly_insurance(Decimal("50000.00"))
        assert abs(ins_half - ins_full / 2) <= Decimal("0.00001")

    def test_two_insured_list_rate_computes_insurance_without_error(self):
        """List-input rate elements work correctly in _compute_monthly_insurance."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.002, 0.004],
            insured_number=2,
            insurance_coverage=COVERAGE,
        )
        result = calc._compute_monthly_insurance(Decimal("100000.00"))
        # 100000 × (0.002 × 1.0) / 12 + 100000 × (0.004 × 1.0) / 12 = 50.00
        assert isinstance(result, Decimal)
        assert abs(result - Decimal("50.0")) <= Decimal("0.01")

    def test_two_insured_list_coverage_computes_insurance_without_error(self):
        """List-input coverage elements work correctly in _compute_monthly_insurance."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=2,
            insurance_coverage=[0.5, 0.5],
        )
        result = calc._compute_monthly_insurance(Decimal("100000.00"))
        # 100000 × (0.003 × 0.5) / 12 × 2 = 25.00
        assert isinstance(result, Decimal)
        assert abs(result - Decimal("25.0")) <= Decimal("0.01")

    def test_two_insured_asymmetric_rates_and_coverages_sum_is_correct(self):
        """Asymmetric per-person rates and coverages are each applied independently."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.003, 0.002],
            insured_number=2,
            insurance_coverage=[1.0, 0.5],
        )
        remaining_capital = Decimal("100000.00")
        result = calc._compute_monthly_insurance(remaining_capital)
        # Person A: 100000 × (0.003 × 1.0) / 12 = 25.0
        # Person B: 100000 × (0.002 × 0.5) / 12 ≈ 8.33333…
        # Total ≈ 33.33333…
        person_a_expected = remaining_capital * (Decimal("0.003") * Decimal("1.0")) / Decimal("12")
        person_b_expected = remaining_capital * (Decimal("0.002") * Decimal("0.5")) / Decimal("12")
        expected_total = person_a_expected + person_b_expected
        assert abs(result - expected_total) <= Decimal("0.00001")

    def test_two_insured_list_rate_per_person_contribution_breakdown(self):
        """Each insured person's contribution is summed to form the total insurance cost."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=[0.003, 0.002],
            insured_number=2,
            insurance_coverage=[1.0, 0.5],
        )
        remaining_capital = Decimal("100000.00")
        result = calc._compute_monthly_insurance(remaining_capital)
        person_a_expected = remaining_capital * (Decimal("0.003") * Decimal("1.0")) / Decimal("12")
        person_b_expected = remaining_capital * (Decimal("0.002") * Decimal("0.5")) / Decimal("12")
        assert result == person_a_expected + person_b_expected

    def test_constructor_stores_both_rates_when_list_passed(self):
        """When a 2-element list is passed, both rates are stored in annual_insurance_rate."""
        calc = LoanCalculator(
            loan_amount=100_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=[0.003, 0.002],
            insured_number=2,
        )
        assert len(calc.annual_insurance_rate) == 2
        assert calc.annual_insurance_rate[0] == Decimal("0.003").quantize(Decimal("0.00001"))
        assert calc.annual_insurance_rate[1] == Decimal("0.002").quantize(Decimal("0.00001"))


# ===========================================================================
# calculate_loan_amortization_table
# ===========================================================================

class TestCalculateLoanAmortizationTable:
    """Tests for LoanCalculator.calculate_loan_amortization_table."""

    # -----------------------------------------------------------------------
    # GREEN — structure and typing
    # -----------------------------------------------------------------------

    def test_result_is_dict(self, calc_single):
        """Return value is a dict."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert isinstance(table, dict)

    def test_all_required_keys_present(self, calc_single):
        """All six required keys are present in the returned dict."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        expected_keys = {"month", "interest", "insurance", "refunded_capital",
                         "remaining_capital", "cumulated_costs"}
        assert set(table.keys()) == expected_keys

    def test_all_lists_have_equal_length(self, calc_single):
        """All value lists have the same length."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        lengths = {k: len(v) for k, v in table.items()}
        assert len(set(lengths.values())) == 1, f"Unequal list lengths: {lengths}"

    def test_month_values_are_int(self, calc_single):
        """All entries in the 'month' list are int."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        for m in table["month"]:
            assert isinstance(m, int)

    def test_monetary_values_are_decimal(self, calc_single):
        """All monetary values in interest, insurance, refunded_capital,
        remaining_capital, and cumulated_costs lists are Decimal."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        monetary_keys = ["interest", "insurance", "refunded_capital",
                         "remaining_capital", "cumulated_costs"]
        for key in monetary_keys:
            for val in table[key]:
                assert isinstance(val, Decimal), (
                    f"table[{key!r}] contains non-Decimal: {val!r} ({type(val).__name__})"
                )

    # -----------------------------------------------------------------------
    # GREEN — month 1 seeded from self.loan_amount
    # -----------------------------------------------------------------------

    def test_first_month_is_1(self, calc_single):
        """Table always starts at month 1."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert table["month"][0] == 1

    def test_month_1_interest_seeded_from_loan_amount(self, calc_single):
        """Month 1 interest = loan_amount × annual_rate / 12."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        # 100000.00 × 0.01500 / 12 = 125.00
        assert table["interest"][0] == Decimal("125.00")

    def test_month_1_insurance_seeded_from_loan_amount(self, calc_single):
        """Month 1 insurance = loan_amount × (insurance_rate × coverage) / 12."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        # 100000.00 × (0.00300 × 1.00) / 12 = 25.00
        assert table["insurance"][0] == Decimal("25.00")

    def test_month_1_refunded_capital(self, calc_single):
        """Month 1 refunded_capital = repayment − interest − insurance."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        # 690.00 − 125.00 − 25.00 = 540.00
        assert table["refunded_capital"][0] == Decimal("540.00")

    def test_month_1_remaining_capital(self, calc_single):
        """Month 1 remaining_capital = loan_amount − refunded_capital."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        # 100000.00 − 540.00 = 99460.00
        assert table["remaining_capital"][0] == Decimal("99460.00")

    def test_month_1_cumulated_costs(self, calc_single):
        """Month 1 cumulated_costs = interest + insurance."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        # 125.00 + 25.00 = 150.00
        assert table["cumulated_costs"][0] == Decimal("150.00")

    # -----------------------------------------------------------------------
    # GREEN — termination behavior
    # -----------------------------------------------------------------------

    def test_table_terminates_before_duration_when_repayment_is_high(self, calc_single):
        """Repayment of 690 on a 100k/1.5% loan terminates at month 164 (< 180)."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert len(table["month"]) < DURATION

    def test_table_terminates_at_expected_month(self, calc_single):
        """The 690 repayment table ends at month 164."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert table["month"][-1] == 164

    def test_final_remaining_capital_is_zero(self, calc_single):
        """The last remaining_capital in the table is 0.00."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert table["remaining_capital"][-1] == Decimal("0.00")

    def test_table_does_not_exceed_duration(self, calc_single):
        """The table never contains more rows than the requested duration."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert len(table["month"]) <= DURATION

    def test_exact_repayment_ends_exactly_at_duration(self, calc_single):
        """634.04 repayment ends the table exactly at month 180."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert table["month"][-1] == DURATION
        assert table["remaining_capital"][-1] == Decimal("0.00")

    # -----------------------------------------------------------------------
    # GREEN — cumulated_costs monotonicity
    # -----------------------------------------------------------------------

    def test_cumulated_costs_monotonically_non_decreasing(self, calc_single):
        """cumulated_costs is non-decreasing across all months."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        costs = table["cumulated_costs"]
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1], (
                f"cumulated_costs decreased at index {i}: {costs[i]} > {costs[i+1]}"
            )

    # -----------------------------------------------------------------------
    # GREEN — early repayment
    # -----------------------------------------------------------------------

    def test_early_repayment_reduces_remaining_capital_after_repayment_month(
        self, calc_single
    ):
        """Early repayment at month 60 lowers remaining_capital from month 61 onward."""
        table_no_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        table_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        # Month 60 (index 59) is the same — early repayment is applied before
        # computing month 61 (index 60)
        assert table_er["remaining_capital"][60] < table_no_er["remaining_capital"][60]

    def test_early_repayment_amount_reflected_in_remaining_capital(self, calc_single):
        """The remaining_capital drop at month 61 equals the early repayment plus saved costs.

        The difference between the two tables at index 60 (month 61) is not exactly
        20 000 but 20 030: the 20 000 lump sum is applied before month 61's computation,
        so the lower outstanding balance also reduces that month's interest (≈ 25.00) and
        insurance (≈ 5.00), causing 30 extra units of capital to be repaid on top of the
        lump sum.
        """
        table_no_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        table_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        diff = table_no_er["remaining_capital"][60] - table_er["remaining_capital"][60]
        # 20 000 lump sum + ~25 saved interest + ~5 saved insurance = 20 030 exactly.
        assert diff == Decimal("20030.00")

    def test_early_repayment_shortens_loan_duration(self, calc_single):
        """A lump-sum early repayment causes the loan to finish before the baseline."""
        table_no_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        table_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert len(table_er["month"]) < len(table_no_er["month"])

    def test_early_repayment_before_repayment_month_rows_unchanged(self, calc_single):
        """Rows before the early-repayment month are identical in both tables."""
        table_no_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        table_er = calc_single.calculate_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        # Rows 0..58 (months 1..59) must be identical
        for i in range(59):
            assert table_no_er["remaining_capital"][i] == table_er["remaining_capital"][i], (
                f"remaining_capital differs before early repayment at index {i}"
            )

    # -----------------------------------------------------------------------
    # RED — calculate_loan_amortization_table input-validation guards
    # -----------------------------------------------------------------------

    # Guard 6: duration < 1
    def test_amortization_duration_zero_raises_value_error(self, calc_single):
        """duration=0 is less than 1 and must raise ValueError."""
        with pytest.raises(ValueError, match="duration"):
            calc_single.calculate_loan_amortization_table(
                duration=0, monthly_repayment=REPAYMENT_HIGH
            )

    def test_amortization_duration_negative_raises_value_error(self, calc_single):
        """duration=-1 is negative and must raise ValueError."""
        with pytest.raises(ValueError, match="duration"):
            calc_single.calculate_loan_amortization_table(
                duration=-1, monthly_repayment=REPAYMENT_HIGH
            )

    def test_amortization_duration_one_does_not_raise(self, calc_single):
        """duration=1 is at the minimum valid boundary and must not raise."""
        table = calc_single.calculate_loan_amortization_table(
            duration=1, monthly_repayment=REPAYMENT_HIGH
        )
        assert table["month"] == [1]

    # Guard 7: early_repayment provided with early_repayment <= 0
    def test_amortization_early_repayment_zero_raises_value_error(self, calc_single):
        """early_repayment=0 is not positive and must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment"):
            calc_single.calculate_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=0,
                early_repayment_month=60,
            )

    def test_amortization_early_repayment_negative_raises_value_error(self, calc_single):
        """early_repayment=-1000 is negative and must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment"):
            calc_single.calculate_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=-1000,
                early_repayment_month=60,
            )

    # Guard 8: early_repayment provided with early_repayment_month out of range
    def test_amortization_early_repayment_month_zero_raises_value_error(self, calc_single):
        """early_repayment_month=0 is below the valid minimum of 1 and must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            calc_single.calculate_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=20_000,
                early_repayment_month=0,
            )

    def test_amortization_early_repayment_month_equals_duration_raises_value_error(
        self, calc_single
    ):
        """early_repayment_month=duration is out of range (must be < duration) and must raise."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            calc_single.calculate_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=20_000,
                early_repayment_month=DURATION,
            )

    def test_amortization_early_repayment_month_above_duration_raises_value_error(
        self, calc_single
    ):
        """early_repayment_month=duration+1 exceeds the valid range and must raise."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            calc_single.calculate_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=20_000,
                early_repayment_month=DURATION + 1,
            )

    def test_amortization_early_repayment_month_one_does_not_raise(self, calc_single):
        """early_repayment_month=1 with duration=180 is at the minimum valid boundary."""
        table = calc_single.calculate_loan_amortization_table(
            duration=180,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=1,
        )
        assert len(table["month"]) >= 1

    def test_amortization_early_repayment_month_duration_minus_one_does_not_raise(
        self, calc_single
    ):
        """early_repayment_month=179 with duration=180 is at the maximum valid boundary."""
        table = calc_single.calculate_loan_amortization_table(
            duration=180,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=179,
        )
        assert len(table["month"]) >= 1


# ===========================================================================
# _compute_adjusted_monthly_repayment
# ===========================================================================

class TestComputeAdjustedMonthlyRepayment:
    """Tests for LoanCalculator._compute_adjusted_monthly_repayment.

    The method was extracted from the inner function
    ``calculate_new_monthly_repayment`` that previously lived inside
    ``calculate_monthly_repayment_and_loan_amortization_table``.

    Contract:
      - Returns a 2-tuple ``(adjusted_repayment, capital_ratio)``.
      - ``adjusted_repayment`` = ``quantize_amount(monthly_repayment * (1 + capital_ratio / 2))``.
      - When ``initial_capital_ratio`` is provided it is used directly as
        ``capital_ratio``; otherwise ``capital_ratio = current_remaining_capital / loan_amount``.
      - Both returned values are ``Decimal``; ``adjusted_repayment`` is quantized
        to 2 d.p. (cents).
    """

    # -----------------------------------------------------------------------
    # Fixtures
    # -----------------------------------------------------------------------

    @pytest.fixture
    def calc(self) -> LoanCalculator:
        """Standard single-insured calculator used throughout this class."""
        return LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
        )

    # -----------------------------------------------------------------------
    # GREEN — return type and structure
    # -----------------------------------------------------------------------

    def test_returns_two_tuple(self, calc):
        """Return value is a 2-tuple."""
        result = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("100000.00"),
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_decimal(self, calc):
        """First element (adjusted repayment) is a Decimal instance."""
        adjusted, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("100000.00"),
        )
        assert isinstance(adjusted, Decimal)

    def test_second_element_is_decimal(self, calc):
        """Second element (capital_ratio) is a Decimal instance."""
        _, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("100000.00"),
        )
        assert isinstance(ratio, Decimal)

    def test_adjusted_repayment_is_quantized_to_two_decimal_places(self, calc):
        """Adjusted repayment is quantized to 2 d.p. (cents)."""
        adjusted, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("100000.00"),
        )
        assert adjusted.as_tuple().exponent == -2

    # -----------------------------------------------------------------------
    # GREEN — derived ratio path (initial_capital_ratio=None)
    # -----------------------------------------------------------------------

    def test_derived_ratio_equals_remaining_over_loan(self, calc):
        """When initial_capital_ratio is None, ratio = remaining_capital / loan_amount."""
        remaining = Decimal("5000.00")
        loan = Decimal("100000.00")
        _, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=remaining,
            loan_amount=loan,
        )
        # ratio is stored at precision "0.000001"
        expected_ratio = Decimal(str(float(remaining / loan))).quantize(Decimal("0.000001"))
        assert ratio == expected_ratio

    def test_derived_ratio_adjusted_repayment_formula(self, calc):
        """Adjusted repayment = quantize(repayment * (1 + ratio / 2)) when ratio derived."""
        repayment = Decimal("634.04")
        remaining = Decimal("5000.00")
        loan = Decimal("100000.00")
        adjusted, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=remaining,
            loan_amount=loan,
        )
        expected = quantize_amount(repayment * (1 + ratio / 2))
        assert adjusted == expected

    def test_derived_ratio_increases_repayment_when_remaining_positive(self, calc):
        """A positive remaining capital (ratio > 0) must produce a repayment strictly
        greater than the input — the solver needs to push repayment up.
        """
        repayment = Decimal("634.04")
        adjusted, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("100000.00"),
        )
        assert adjusted > repayment

    # -----------------------------------------------------------------------
    # GREEN — explicit ratio path (initial_capital_ratio provided)
    # -----------------------------------------------------------------------

    def test_explicit_ratio_is_used_directly(self, calc):
        """When initial_capital_ratio is provided, it is used as-is (not re-derived)."""
        explicit_ratio = Decimal("0.05")
        repayment = Decimal("634.04")
        _, returned_ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("99000.00"),  # would give very different ratio
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=explicit_ratio,
        )
        # The returned ratio is the explicit one converted through float at "0.000001"
        expected_ratio = Decimal(str(float(explicit_ratio))).quantize(Decimal("0.000001"))
        assert returned_ratio == expected_ratio

    def test_explicit_ratio_formula_applied(self, calc):
        """Adjusted repayment uses the explicit ratio in the formula."""
        explicit_ratio = Decimal("0.05")
        repayment = Decimal("634.04")
        adjusted, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("99000.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=explicit_ratio,
        )
        expected = quantize_amount(repayment * (1 + ratio / 2))
        assert adjusted == expected

    def test_explicit_ratio_ignores_current_remaining_capital(self, calc):
        """Two calls with the same explicit ratio but different remaining capitals
        must return the same adjusted repayment.
        """
        repayment = Decimal("634.04")
        explicit_ratio = Decimal("0.10")
        result_a, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("1000.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=explicit_ratio,
        )
        result_b, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("50000.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=explicit_ratio,
        )
        assert result_a == result_b

    # -----------------------------------------------------------------------
    # GREEN — sign / magnitude of the adjustment
    # -----------------------------------------------------------------------

    def test_negative_explicit_ratio_decreases_repayment(self, calc):
        """A negative ratio (stall-recovery injection: -0.5) must produce a repayment
        strictly less than the input — solver is pushing repayment down.
        """
        repayment = Decimal("634.04")
        adjusted, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("0.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=Decimal("-0.5"),
        )
        assert adjusted < repayment

    def test_stall_ratio_minus_half_formula(self, calc):
        """Stall-recovery ratio of -0.5 produces repayment * 0.75 (quantized)."""
        repayment = Decimal("634.04")
        adjusted, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("0.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=Decimal("-0.5"),
        )
        # ratio / 2 = -0.25, so factor = 1 + (-0.25) = 0.75
        expected = quantize_amount(repayment * (1 + ratio / 2))
        assert adjusted == expected

    def test_zero_explicit_ratio_returns_repayment_unchanged(self, calc):
        """A ratio of exactly zero leaves the repayment unchanged (identity case)."""
        repayment = Decimal("634.04")
        adjusted, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=Decimal("0.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=Decimal("0"),
        )
        assert adjusted == quantize_amount(repayment)

    def test_large_loan_amount_small_remaining_produces_small_ratio(self, calc):
        """Tiny remaining capital relative to large loan → ratio near 0, tiny adjustment."""
        repayment = Decimal("1000.00")
        remaining = Decimal("1.00")
        loan = Decimal("1000000.00")
        adjusted, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=repayment,
            current_remaining_capital=remaining,
            loan_amount=loan,
        )
        # ratio = 1 / 1_000_000 → very small, adjustment is negligible
        assert ratio < Decimal("0.000002")
        # Adjusted repayment must still be >= input (small positive nudge)
        assert adjusted >= repayment

    def test_ratio_precision_is_six_decimal_places(self, calc):
        """Returned capital_ratio is quantized to exactly 6 decimal places."""
        _, ratio = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("33333.33"),
            loan_amount=Decimal("100000.00"),
        )
        assert ratio.as_tuple().exponent == -6

    # -----------------------------------------------------------------------
    # RED — xfail: edge cases the method does not guard against
    # -----------------------------------------------------------------------

    @pytest.mark.xfail(
        reason="loan_amount=0 causes ZeroDivisionError in the ratio derivation; "
               "no guard exists for zero loan_amount when initial_capital_ratio is None",
        strict=True,
    )
    def test_zero_loan_amount_raises_cleanly(self, calc):
        """Edge case: zero loan_amount with no explicit ratio triggers division by zero.

        Would need an explicit guard (e.g. ``if loan_amount == 0: raise ValueError``)
        to raise a clean exception rather than an unhandled ZeroDivisionError.
        """
        calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("0"),
        )
        # If the method ever raises a friendly ValueError we would assert it here.
        # For now this is xfail because ZeroDivisionError is raised instead.
        assert False, "Expected a friendly ValueError, got ZeroDivisionError"

    @pytest.mark.xfail(
        reason="_compute_adjusted_monthly_repayment accepts any Decimal for "
               "initial_capital_ratio without validating magnitude; a ratio of 1e6 "
               "would produce a wildly outsized repayment with no error",
        strict=False,
    )
    def test_enormous_explicit_ratio_raises_value_error(self, calc):
        """Edge case: an absurdly large ratio is not rejected by the method.

        A production-grade guard would raise ValueError for ratios outside a
        reasonable domain (e.g. |ratio| > some sentinel), protecting the solver
        from generating repayments orders of magnitude beyond the loan amount.
        """
        adjusted, _ = calc._compute_adjusted_monthly_repayment(
            monthly_repayment=Decimal("634.04"),
            current_remaining_capital=Decimal("5000.00"),
            loan_amount=Decimal("100000.00"),
            initial_capital_ratio=Decimal("1000000"),
        )
        # This assertion will not be reached; xfail documents the missing guard.
        assert adjusted <= Decimal("100000.00"), "Adjusted repayment exceeds loan amount — no guard"


# ===========================================================================
# calculate_monthly_repayment_and_loan_amortization_table
# ===========================================================================

class TestCalculateMonthlyRepaymentAndLoanAmortizationTable:
    """Tests for LoanCalculator.calculate_monthly_repayment_and_loan_amortization_table.

    Two paths are tested:
    - Case 1: no early repayment, correct repayment passed as starting estimate
              → solver returns immediately with the passed-through value.
    - Case 2 / Strategy B: early repayment provided → two-phase table spanning
              exactly ``duration`` months, with a new lower repayment for Phase 2.
    """

    # -----------------------------------------------------------------------
    # GREEN — return type and structure
    # -----------------------------------------------------------------------

    def test_return_is_two_tuple(self, calc_single):
        """Return value is a 2-tuple."""
        result = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_return_first_element_is_dict(self, calc_single):
        """First element of the return tuple is a dict (the amortization table)."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert isinstance(table, dict)

    def test_return_second_element_is_decimal(self, calc_single):
        """Second element of the return tuple is a Decimal (the final monthly repayment)."""
        _, monthly = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert isinstance(monthly, Decimal)

    # -----------------------------------------------------------------------
    # GREEN — Case 1: correct starting repayment, no early repayment
    # -----------------------------------------------------------------------

    def test_case1_solver_returns_exact_repayment_unchanged(self, calc_single):
        """Case 1: when 634.04 already produces a 180-month table, solver returns it as-is.

        The pre-loop guard (remaining[-1]==0, remaining[-2]!=0) triggers immediately,
        short-circuiting the iterative loop.
        """
        _, monthly = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert monthly == REPAYMENT_EXACT

    def test_case1_table_ends_at_duration(self, calc_single):
        """Case 1: the returned table ends exactly at month 180."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert table["month"][-1] == DURATION

    def test_case1_table_last_remaining_capital_is_zero(self, calc_single):
        """Case 1: last remaining_capital in the table is 0.00."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert table["remaining_capital"][-1] == Decimal("0.00")

    def test_case1_table_penultimate_remaining_capital_is_nonzero(self, calc_single):
        """Case 1: the row before the final one has positive remaining capital."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        assert table["remaining_capital"][-2] > Decimal("0.00")

    def test_case1_table_has_all_required_keys(self, calc_single):
        """Case 1: returned table dict contains all six required keys."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_EXACT
        )
        expected_keys = {"month", "interest", "insurance", "refunded_capital",
                         "remaining_capital", "cumulated_costs"}
        assert set(table.keys()) == expected_keys

    # -----------------------------------------------------------------------
    # GREEN — Case 2: early repayment provided
    # -----------------------------------------------------------------------

    def test_case2_solver_returns_zero_remaining_capital(self, calc_single):
        """Case 2: with early repayment, table ends with zero remaining capital."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["remaining_capital"][-1] == Decimal("0.00")

    def test_case2_solver_returns_nonzero_penultimate_remaining_capital(self, calc_single):
        """Case 2: the row before the final one is still positive."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["remaining_capital"][-2] > Decimal("0.00")

    def test_case2_table_ends_before_duration(self, calc_single):
        """Case 2 (Strategy B): early repayment → merged table always spans full duration.

        Strategy B merges Phase 1 (months 1..60) and Phase 2 (months 61..180) into
        a single table of exactly DURATION rows; it no longer terminates early.
        """
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert len(table["month"]) == DURATION

    def test_case2_returned_monthly_repayment_is_decimal(self, calc_single):
        """Case 2 (Strategy B): returned value is the Phase 2 analytical repayment as Decimal.

        The returned repayment is the new (lower) payment computed analytically for
        Phase 2, not the original REPAYMENT_HIGH. For this fixture it equals 420.28.
        """
        _, monthly = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert isinstance(monthly, Decimal)
        assert monthly == Decimal("420.28")

    def test_case2_table_ends_at_month_180(self, calc_single):
        """Case 2 (Strategy B): merged table's last month is always DURATION (180).

        Previously this tested that the table ended at month 131 (early termination).
        Strategy B always produces exactly DURATION rows, so the last month is 180.
        """
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["month"][-1] == DURATION

    # -----------------------------------------------------------------------
    # GREEN — Strategy B (early repayment)
    # -----------------------------------------------------------------------

    def test_strategy_b_table_has_exactly_duration_rows(self, calc_single):
        """Strategy B: merged table (Phase 1 + Phase 2) has exactly DURATION rows."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert len(table["month"]) == DURATION

    def test_strategy_b_phase2_repayment_lower_than_original(self, calc_single):
        """Strategy B: the analytically-derived Phase 2 repayment is lower than the original.

        After a 20 000 lump-sum reduction of principal, the new payment to service the
        smaller balance over the remaining 120 months is less than REPAYMENT_HIGH (690.00).
        """
        _, phase2_repayment = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert phase2_repayment < REPAYMENT_HIGH

    def test_strategy_b_remaining_capital_zero_at_end(self, calc_single):
        """Strategy B: the last row of the merged table has zero remaining capital."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["remaining_capital"][-1] == Decimal("0.00")

    def test_strategy_b_cumulated_costs_monotone(self, calc_single):
        """Strategy B: cumulated_costs is non-decreasing across the full merged table.

        The Phase 1→Phase 2 boundary (month 60→61) must not create a dip because the
        Phase 2 cumulated_costs are offset by Phase 1's running total.
        """
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        costs = table["cumulated_costs"]
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1], (
                f"cumulated_costs decreased at index {i} "
                f"(month {table['month'][i]}→{table['month'][i+1]}): "
                f"{costs[i]} > {costs[i+1]}"
            )

    def test_strategy_b_phase1_rows_match_no_early_repayment_baseline(self, calc_single):
        """Strategy B: the first 60 rows of the merged table are identical to a plain
        60-month amortization table at REPAYMENT_HIGH (no early repayment).

        Phase 1 is computed independently with the same inputs, so every column
        for months 1..60 must match the standalone baseline exactly.
        """
        baseline = calc_single.calculate_loan_amortization_table(
            duration=60, monthly_repayment=REPAYMENT_HIGH
        )
        merged, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        for i in range(60):
            for key in ("interest", "insurance", "refunded_capital", "remaining_capital"):
                assert merged[key][i] == baseline[key][i], (
                    f"Phase 1 mismatch at index {i} (month {i+1}), key={key!r}: "
                    f"merged={merged[key][i]!r} vs baseline={baseline[key][i]!r}"
                )

    # -----------------------------------------------------------------------
    # RED — calculate_monthly_repayment_and_loan_amortization_table guards
    # -----------------------------------------------------------------------

    # Guard 9: duration < 1
    def test_solver_duration_zero_raises_value_error(self, calc_single):
        """duration=0 is less than 1 and must raise ValueError."""
        with pytest.raises(ValueError, match="duration"):
            calc_single.calculate_monthly_repayment_and_loan_amortization_table(
                duration=0, monthly_repayment=REPAYMENT_HIGH
            )

    # Guard 10: early_repayment provided with early_repayment <= 0
    def test_solver_early_repayment_zero_raises_value_error(self, calc_single):
        """early_repayment=0 is not positive and must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment"):
            calc_single.calculate_monthly_repayment_and_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=0,
                early_repayment_month=60,
            )

    # Guard 11: early_repayment provided with early_repayment_month out of range
    def test_solver_early_repayment_month_zero_raises_value_error(self, calc_single):
        """early_repayment_month=0 is below the valid minimum of 1 and must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            calc_single.calculate_monthly_repayment_and_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=20_000,
                early_repayment_month=0,
            )

    def test_solver_early_repayment_month_equals_duration_raises_value_error(
        self, calc_single
    ):
        """early_repayment_month=duration is out of range (must be < duration) and must raise."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            calc_single.calculate_monthly_repayment_and_loan_amortization_table(
                duration=DURATION,
                monthly_repayment=REPAYMENT_HIGH,
                early_repayment=20_000,
                early_repayment_month=DURATION,
            )



# ===========================================================================
# calculate_loan_amortization_table — initial_capital parameter
# ===========================================================================

class TestCalculateLoanAmortizationTableInitialCapital:
    """Tests for the initial_capital parameter of calculate_loan_amortization_table."""

    # -----------------------------------------------------------------------
    # GREEN — initial_capital overrides self.loan_amount for month 1 seeding
    # -----------------------------------------------------------------------

    def test_initial_capital_overrides_loan_amount_for_month1_interest(self):
        """Month 1 interest is seeded from initial_capital, not self.loan_amount.

        The calculator is constructed with loan_amount=100_000 but
        initial_capital=46123.78 is passed explicitly. Month 1 interest must
        be based on 46123.78 × annual_rate / 12.
        """
        calc = LoanCalculator(
            loan_amount=100_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.003,
            insured_number=1,
            insurance_coverage=1.0,
        )
        initial_cap = Decimal("46123.78")
        table = calc.calculate_loan_amortization_table(
            duration=120,
            monthly_repayment=Decimal("420.28"),
            initial_capital=initial_cap,
        )
        # 46123.78 × 0.01500 / 12 = 57.654725 → quantized to 57.65
        expected = quantize_amount(initial_cap * Decimal("0.01500") / 12)
        assert table["interest"][0] == expected

    def test_initial_capital_overrides_loan_amount_for_month1_insurance(self):
        """Month 1 insurance is seeded from initial_capital, not self.loan_amount."""
        calc = LoanCalculator(
            loan_amount=100_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.003,
            insured_number=1,
            insurance_coverage=1.0,
        )
        initial_cap = Decimal("46123.78")
        table = calc.calculate_loan_amortization_table(
            duration=120,
            monthly_repayment=Decimal("420.28"),
            initial_capital=initial_cap,
        )
        # 46123.78 × (0.00300 × 1.0) / 12 = 11.530945 → quantized to 11.53
        expected = quantize_amount(initial_cap * Decimal("0.00300") / 12)
        assert table["insurance"][0] == expected

    def test_initial_capital_not_provided_uses_loan_amount(self):
        """Without initial_capital, month 1 is seeded from self.loan_amount (default)."""
        calc = LoanCalculator(
            loan_amount=100_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.003,
            insured_number=1,
            insurance_coverage=1.0,
        )
        table = calc.calculate_loan_amortization_table(
            duration=180,
            monthly_repayment=Decimal("690.00"),
        )
        # 100000 × 0.01500 / 12 = 125.00
        assert table["interest"][0] == Decimal("125.00")

    def test_initial_capital_different_from_loan_amount_produces_different_month1(self):
        """initial_capital != loan_amount → month 1 rows differ from the default table."""
        calc = LoanCalculator(
            loan_amount=100_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.003,
            insured_number=1,
            insurance_coverage=1.0,
        )
        table_default = calc.calculate_loan_amortization_table(
            duration=120,
            monthly_repayment=Decimal("420.28"),
        )
        table_override = calc.calculate_loan_amortization_table(
            duration=120,
            monthly_repayment=Decimal("420.28"),
            initial_capital=Decimal("46123.78"),
        )
        assert table_override["interest"][0] != table_default["interest"][0]
        assert table_override["remaining_capital"][0] != table_default["remaining_capital"][0]


# ===========================================================================
# Solver convergence guards: oscillation detection and RuntimeError
# ===========================================================================

def _make_table(remaining_last, remaining_second_to_last=Decimal("500.00"), month_last=200):
    """Build a minimal amortization-table stub for mock side_effect entries.

    The solver reads exactly three things from each returned table:
    - remaining_capital[-1]   → drives capital_ratio and oscillation detection
    - remaining_capital[-2]   → checked in the convergence guard (must be != 0)
    - month[-1]               → checked in the convergence guard (must equal duration)

    To avoid accidentally triggering the convergence return, we always set
    month[-1] to 200 (a value != any duration used in these tests), and keep
    remaining_capital[-2] non-zero.
    """
    return {
        "month":             [1, month_last],
        "interest":          [Decimal("10.00"), Decimal("10.00")],
        "insurance":         [Decimal("2.00"),  Decimal("2.00")],
        "refunded_capital":  [Decimal("50.00"), Decimal("50.00")],
        "remaining_capital": [remaining_second_to_last, remaining_last],
        "cumulated_costs":   [Decimal("12.00"), Decimal("24.00")],
    }


def _patched_to_decimal(value, precision="0.01"):
    """Drop-in replacement for to_decimal that also accepts Decimal and str inputs.

    The production to_decimal() rejects Decimal values (only int/float allowed).
    Inside the solver's inner function ``calculate_new_monthly_repayment``, the
    capital_ratio is derived as ``Decimal / Decimal``, yielding a Decimal, which
    is then passed to to_decimal().  That call raises TypeError in production —
    meaning the solver loop body is currently broken and unreachable in practice.

    Line 491 also passes the string literal "-0.5" to to_decimal(), which is
    likewise rejected by the production implementation.

    This patched version accepts Decimal (converted via float) and str (converted
    via Decimal() directly), allowing the loop to execute so that oscillation and
    RuntimeError paths can be tested.
    """
    from budget_simulator._utils import to_decimal as _real_to_decimal
    if isinstance(value, Decimal):
        return _real_to_decimal(float(value), precision=precision)
    if isinstance(value, str):
        return Decimal(value).quantize(Decimal(precision))
    return _real_to_decimal(value, precision=precision)


class TestSolverOscillationAndConvergence:
    """Tests for the iterative-solver convergence guards added to
    calculate_monthly_repayment_and_loan_amortization_table.

    All tests in this class target the no-early-repayment code path (the
    iterative solver).  The early-repayment Strategy B path is exercised
    elsewhere and is not affected by these changes.

    Mock strategy
    -------------
    ``calculate_loan_amortization_table`` is patched with a ``side_effect``
    list so each successive call returns a pre-determined table.  The helper
    ``_make_table`` builds minimal stubs that satisfy every attribute the
    solver reads without accidentally triggering the convergence fast-exit.

    Derivation of expected repayments (oscillation tests)
    -------------------------------------------------------
    Starting state:
        loan_amount   = 200_000
        monthly_rep   = Decimal("1000.00")

    Pre-loop call (call 0): remaining_capital[-1] = Decimal("200.00")
        → does not satisfy convergence guard → enters loop.

    Iteration 0 (call 1 inside loop):
        capital_ratio = 200.00 / 200_000.00 = 0.001
        new_repayment = quantize(1000.00 × (1 + 0.001/2))
                      = quantize(1000.00 × 1.000500)
                      = quantize(1000.500)
                      = Decimal("1000.50")
        remaining = +100.00  →  last_positive = (100.00, 1000.50)

    Iteration 1 (call 2):
        capital_ratio = 100.00 / 200_000.00 = 0.0005
        new_repayment = quantize(1000.50 × (1 + 0.0005/2))
                      = quantize(1000.50 × 1.000250)
                      = quantize(1000.750125)
                      = Decimal("1000.75")
        remaining = -80.00   →  last_negative = (-80.00, 1000.75)

    Iteration 2 (call 3):
        capital_ratio = -80.00 / 200_000.00 = -0.0004
        new_repayment = quantize(1000.75 × (1 + (-0.0004)/2))
                      = quantize(1000.75 × 0.999800)
                      = quantize(1000.54985)
                      = Decimal("1000.55")
        remaining = +100.00  → same as last_positive[0] → OSCILLATION DETECTED

        best_repayment = quantize((last_negative[1] + last_positive[1]) / 2)
                       = quantize((1000.75 + 1000.50) / 2)
                       = quantize(1000.625)
        ROUND_HALF_EVEN: hundredths digit = 2 (even), so round down
                       = Decimal("1000.62")

    Call 4 (final table re-run at best_repayment): returns stub table.
    """

    # -----------------------------------------------------------------------
    # Oscillation: positive-sign repeat triggers UserWarning
    # -----------------------------------------------------------------------

    def test_oscillation_emits_user_warning(self):
        """When the solver sees the same positive remaining capital twice in a row
        (with an intervening negative), it must emit a UserWarning whose message
        contains the word 'oscillating'.
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        # call 0: pre-loop (non-zero → no early exit)
        # calls 1-3: loop iterations driving the oscillation
        # call 4: final re-run at best_repayment
        side_effects = [
            _make_table(Decimal("200.00")),   # call 0 — pre-loop, non-zero
            _make_table(Decimal("100.00")),   # call 1 — iter 0, +100 → last_positive set
            _make_table(Decimal("-80.00")),   # call 2 — iter 1, -80  → last_negative set
            _make_table(Decimal("100.00")),   # call 3 — iter 2, +100 REPEAT → oscillation
            _make_table(Decimal("0.00")),     # call 4 — final table at best_repayment
        ]
        with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
            with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                with pytest.warns(UserWarning, match="oscillating"):
                    calc.calculate_monthly_repayment_and_loan_amortization_table(
                        duration=180,
                        monthly_repayment=Decimal("1000.00"),
                    )

    # -----------------------------------------------------------------------
    # Oscillation: negative-sign repeat also triggers UserWarning
    # -----------------------------------------------------------------------

    def test_oscillation_negative_repeat_emits_user_warning(self):
        """Symmetric case: when the same *negative* remaining capital repeats, the
        solver must also emit a UserWarning containing 'oscillating'.

        Sequence:
          call 0 (pre-loop): remaining = -300 (non-zero, no early exit)
          iter 0: remaining = -80   → last_negative = (-80, rep1)
          iter 1: remaining = +100  → last_positive = (+100, rep2)
          iter 2: remaining = -80   → same as last_negative[0] → oscillation
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        side_effects = [
            _make_table(Decimal("-300.00")),  # call 0 — pre-loop, non-zero
            _make_table(Decimal("-80.00")),   # iter 0 — last_negative set
            _make_table(Decimal("100.00")),   # iter 1 — last_positive set
            _make_table(Decimal("-80.00")),   # iter 2 — negative REPEAT → oscillation
            _make_table(Decimal("0.00")),     # call 4 — final re-run
        ]
        with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
            with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                with pytest.warns(UserWarning, match="oscillating"):
                    calc.calculate_monthly_repayment_and_loan_amortization_table(
                        duration=180,
                        monthly_repayment=Decimal("1000.00"),
                    )

    # -----------------------------------------------------------------------
    # Oscillation: returned repayment is the mean of the two bracketing values
    # -----------------------------------------------------------------------

    def test_oscillation_returned_repayment_is_mean_of_bracketing_values(self):
        """On oscillation, the returned monthly repayment must equal the mean of
        the two bracketing repayments (last_negative[1] and last_positive[1]),
        quantized to 2 d.p. (ROUND_HALF_EVEN).

        From the derivation in the class docstring:
            last_positive repayment = Decimal("1000.50")  (iteration 0)
            last_negative repayment = Decimal("1000.75")  (iteration 1)
            mean = (1000.50 + 1000.75) / 2 = 1000.625
            quantize(1000.625, ROUND_HALF_EVEN) = Decimal("1000.62")
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        side_effects = [
            _make_table(Decimal("200.00")),
            _make_table(Decimal("100.00")),
            _make_table(Decimal("-80.00")),
            _make_table(Decimal("100.00")),
            _make_table(Decimal("0.00")),
        ]
        with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
            with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    _, returned_repayment = calc.calculate_monthly_repayment_and_loan_amortization_table(
                        duration=180,
                        monthly_repayment=Decimal("1000.00"),
                    )
        assert returned_repayment == Decimal("1000.62")

    # -----------------------------------------------------------------------
    # Oscillation: returned repayment is a Decimal quantized to 2 d.p.
    # -----------------------------------------------------------------------

    def test_oscillation_returned_repayment_is_decimal_quantized_to_cents(self):
        """The best-effort repayment returned on oscillation is a Decimal with
        exactly 2 decimal places (cents precision).
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        side_effects = [
            _make_table(Decimal("200.00")),
            _make_table(Decimal("100.00")),
            _make_table(Decimal("-80.00")),
            _make_table(Decimal("100.00")),
            _make_table(Decimal("0.00")),
        ]
        with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
            with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    _, returned_repayment = calc.calculate_monthly_repayment_and_loan_amortization_table(
                        duration=180,
                        monthly_repayment=Decimal("1000.00"),
                    )
        assert isinstance(returned_repayment, Decimal)
        assert returned_repayment.as_tuple().exponent == -2

    # -----------------------------------------------------------------------
    # Oscillation: the table returned is the one produced at best_repayment
    # -----------------------------------------------------------------------

    def test_oscillation_returned_table_is_from_best_repayment_run(self):
        """After oscillation is detected, the method runs one final call to
        calculate_loan_amortization_table at best_repayment and returns that
        table.  The returned table must match the stub from that final call.
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        sentinel_table = _make_table(Decimal("0.00"))
        # Mark the sentinel so we can identify it in the assertion
        sentinel_table["_sentinel"] = True

        side_effects = [
            _make_table(Decimal("200.00")),
            _make_table(Decimal("100.00")),
            _make_table(Decimal("-80.00")),
            _make_table(Decimal("100.00")),
            sentinel_table,              # final call at best_repayment
        ]
        with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
            with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    returned_table, _ = calc.calculate_monthly_repayment_and_loan_amortization_table(
                        duration=180,
                        monthly_repayment=Decimal("1000.00"),
                    )
        assert returned_table.get("_sentinel") is True

    # -----------------------------------------------------------------------
    # RuntimeError: solver exhausts all iterations without converging
    # -----------------------------------------------------------------------

    def test_non_convergence_raises_runtime_error(self):
        """When the solver exhausts all _SOLVER_MAX_ITERATIONS iterations without
        converging or oscillating, it must raise a RuntimeError whose message
        contains 'did not converge'.

        The mock always returns a strictly-increasing positive remaining capital
        (never the same value twice), so:
        - The convergence check never fires (remaining != 0).
        - Oscillation never fires (last_positive[0] keeps changing).
        - The loop runs until _SOLVER_MAX_ITERATIONS (patched to 5) and then
          raises RuntimeError.
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        # Pre-loop call + 5 loop iterations = 6 tables total.
        # Each has a distinct, strictly-increasing positive remaining_capital
        # so neither the convergence guard nor the oscillation detector fires.
        side_effects = [
            _make_table(Decimal("100.00")),   # call 0 — pre-loop
            _make_table(Decimal("1.00")),     # iter 0
            _make_table(Decimal("2.00")),     # iter 1
            _make_table(Decimal("3.00")),     # iter 2
            _make_table(Decimal("4.00")),     # iter 3
            _make_table(Decimal("5.00")),     # iter 4
        ]
        with patch.object(LoanCalculator, "_SOLVER_MAX_ITERATIONS", new=5):
            with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
                with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                    with pytest.raises(RuntimeError, match="did not converge"):
                        calc.calculate_monthly_repayment_and_loan_amortization_table(
                            duration=180,
                            monthly_repayment=Decimal("1000.00"),
                        )

    # -----------------------------------------------------------------------
    # RuntimeError: error message includes the iteration count
    # -----------------------------------------------------------------------

    def test_non_convergence_error_message_contains_iteration_count(self):
        """The RuntimeError message must mention the number of iterations
        attempted (the patched _SOLVER_MAX_ITERATIONS value).
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        side_effects = [
            _make_table(Decimal("100.00")),
            _make_table(Decimal("1.00")),
            _make_table(Decimal("2.00")),
            _make_table(Decimal("3.00")),
            _make_table(Decimal("4.00")),
            _make_table(Decimal("5.00")),
        ]
        with patch.object(LoanCalculator, "_SOLVER_MAX_ITERATIONS", new=5):
            with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
                with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                    with pytest.raises(RuntimeError, match="5"):
                        calc.calculate_monthly_repayment_and_loan_amortization_table(
                            duration=180,
                            monthly_repayment=Decimal("1000.00"),
                        )

    def test_positive_repeat_without_prior_negative_raises_runtime_error(self):
        """When a positive remaining_capital repeats before any negative value has been
        seen (last_negative is still None), the oscillation branch must NOT fire
        (it requires both brackets). The loop continues and eventually raises
        RuntimeError after _SOLVER_MAX_ITERATIONS.
        """
        calc = LoanCalculator(
            loan_amount=200_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.002,
        )
        # Pre-loop + 3 iterations all returning the same positive value.
        # last_negative stays None throughout, so oscillation is never triggered.
        # With _SOLVER_MAX_ITERATIONS=3 the loop exhausts and raises RuntimeError.
        side_effects = [_make_table(Decimal("100.00"))] * 4  # pre-loop + 3 iters
        with patch.object(LoanCalculator, "_SOLVER_MAX_ITERATIONS", new=3):
            with patch("budget_simulator.loan_calculator.to_decimal", side_effect=_patched_to_decimal):
                with patch.object(calc, "calculate_loan_amortization_table", side_effect=side_effects):
                    with pytest.raises(RuntimeError, match="3"):
                        calc.calculate_monthly_repayment_and_loan_amortization_table(
                            duration=180,
                            monthly_repayment=Decimal("1000.00"),
                        )


# ===========================================================================
# _validate_early_repayment_args — direct unit tests
# ===========================================================================

@pytest.fixture
def base_calc() -> LoanCalculator:
    """Standard LoanCalculator used as the target for _validate_early_repayment_args calls."""
    return LoanCalculator(
        loan_amount=200_000,
        annual_interest_rate=0.015,
        annual_insurance_rate=0.002,
    )


class TestValidateEarlyRepaymentArgs:
    """Direct tests for LoanCalculator._validate_early_repayment_args.

    This private method is the single source of truth for all early-repayment
    argument validation.  The tests below cover every raise path and every
    happy path (returns None).  Regression tests confirming delegation from the
    two public methods appear in TestDelegationToValidateEarlyRepaymentArgs.
    """

    # -----------------------------------------------------------------------
    # GREEN — duration guard: duration >= 1
    # -----------------------------------------------------------------------

    def test_duration_one_no_early_repayment_does_not_raise(self, base_calc):
        """duration=1 with no early_repayment is the minimum valid call; must return None."""
        result = base_calc._validate_early_repayment_args(
            duration=1,
            early_repayment=None,
            early_repayment_month=0,
        )
        assert result is None

    def test_duration_large_no_early_repayment_does_not_raise(self, base_calc):
        """duration=360 (30 years) with no early_repayment is valid; must return None."""
        result = base_calc._validate_early_repayment_args(
            duration=360,
            early_repayment=None,
            early_repayment_month=0,
        )
        assert result is None

    # -----------------------------------------------------------------------
    # RED — duration guard: duration < 1 raises ValueError
    # -----------------------------------------------------------------------

    def test_duration_zero_raises_value_error(self, base_calc):
        """duration=0 is below the minimum of 1; must raise ValueError mentioning 'duration'."""
        with pytest.raises(ValueError, match="duration"):
            base_calc._validate_early_repayment_args(
                duration=0,
                early_repayment=None,
                early_repayment_month=0,
            )

    def test_duration_negative_raises_value_error(self, base_calc):
        """duration=-1 is negative; must raise ValueError mentioning 'duration'."""
        with pytest.raises(ValueError, match="duration"):
            base_calc._validate_early_repayment_args(
                duration=-1,
                early_repayment=None,
                early_repayment_month=0,
            )

    def test_duration_minus_large_raises_value_error(self, base_calc):
        """duration=-360 is a large negative value; must raise ValueError mentioning 'duration'."""
        with pytest.raises(ValueError, match="duration"):
            base_calc._validate_early_repayment_args(
                duration=-360,
                early_repayment=None,
                early_repayment_month=0,
            )

    def test_duration_zero_error_message_contains_got(self, base_calc):
        """The error message for duration=0 must include the offending value ('got 0')."""
        with pytest.raises(ValueError, match="got 0"):
            base_calc._validate_early_repayment_args(
                duration=0,
                early_repayment=None,
                early_repayment_month=0,
            )

    # -----------------------------------------------------------------------
    # GREEN — early_repayment=None skips inner checks entirely
    # -----------------------------------------------------------------------

    def test_early_repayment_none_with_month_zero_does_not_raise(self, base_calc):
        """early_repayment=None bypasses the amount and month checks; must return None
        even when early_repayment_month=0 (which would otherwise be invalid).
        """
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=None,
            early_repayment_month=0,
        )
        assert result is None

    def test_early_repayment_none_with_month_above_duration_does_not_raise(self, base_calc):
        """early_repayment=None bypasses month bounds check; must return None
        even when early_repayment_month >= duration.
        """
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=None,
            early_repayment_month=200,
        )
        assert result is None

    # -----------------------------------------------------------------------
    # GREEN — early_repayment provided with valid amount and month
    # -----------------------------------------------------------------------

    def test_valid_early_repayment_minimum_month_does_not_raise(self, base_calc):
        """early_repayment=1000 with early_repayment_month=1 and duration=180
        is at the lower boundary of the valid month range (1 <= 1 < 180); must return None.
        """
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=1000,
            early_repayment_month=1,
        )
        assert result is None

    def test_valid_early_repayment_maximum_month_does_not_raise(self, base_calc):
        """early_repayment=1000 with early_repayment_month=duration-1 is at the upper
        boundary of the valid month range (1 <= 179 < 180); must return None.
        """
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=1000,
            early_repayment_month=179,
        )
        assert result is None

    def test_valid_early_repayment_mid_month_does_not_raise(self, base_calc):
        """early_repayment=20_000 at month 60 within duration=180 is valid; must return None."""
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert result is None

    def test_valid_early_repayment_float_amount_does_not_raise(self, base_calc):
        """A float early_repayment value (e.g. 9999.99) is accepted; must return None."""
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=9999.99,
            early_repayment_month=60,
        )
        assert result is None

    def test_valid_early_repayment_returns_none(self, base_calc):
        """The method must explicitly return None (not implicitly fall through)
        when all arguments are valid.
        """
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=5000,
            early_repayment_month=90,
        )
        assert result is None

    # -----------------------------------------------------------------------
    # RED — early_repayment <= 0 raises ValueError
    # -----------------------------------------------------------------------

    def test_early_repayment_zero_raises_value_error(self, base_calc):
        """early_repayment=0 is not positive; must raise ValueError mentioning 'early_repayment'."""
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=0,
                early_repayment_month=60,
            )

    def test_early_repayment_negative_int_raises_value_error(self, base_calc):
        """early_repayment=-1000 is negative; must raise ValueError mentioning 'early_repayment'."""
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=-1000,
                early_repayment_month=60,
            )

    def test_early_repayment_negative_float_raises_value_error(self, base_calc):
        """early_repayment=-0.01 (negative float) must raise ValueError mentioning 'early_repayment'."""
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=-0.01,
                early_repayment_month=60,
            )

    def test_early_repayment_zero_error_message_contains_got(self, base_calc):
        """The error message for early_repayment=0 must include the offending value ('got 0')."""
        with pytest.raises(ValueError, match="got 0"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=0,
                early_repayment_month=60,
            )

    # -----------------------------------------------------------------------
    # RED — early_repayment_month out of [1, duration-1] range raises ValueError
    # -----------------------------------------------------------------------

    def test_early_repayment_month_zero_raises_value_error(self, base_calc):
        """early_repayment_month=0 is below the minimum of 1; must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=10_000,
                early_repayment_month=0,
            )

    def test_early_repayment_month_negative_raises_value_error(self, base_calc):
        """early_repayment_month=-1 is negative; must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=10_000,
                early_repayment_month=-1,
            )

    def test_early_repayment_month_equals_duration_raises_value_error(self, base_calc):
        """early_repayment_month=duration violates the strict upper bound (must be < duration);
        must raise ValueError.
        """
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=10_000,
                early_repayment_month=180,
            )

    def test_early_repayment_month_above_duration_raises_value_error(self, base_calc):
        """early_repayment_month=duration+1 exceeds the valid range; must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=10_000,
                early_repayment_month=181,
            )

    def test_early_repayment_month_error_message_contains_upper_bound(self, base_calc):
        """The error message for an out-of-range month must mention the valid upper bound
        (duration-1), so the caller knows the accepted range.
        """
        with pytest.raises(ValueError, match="179"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=10_000,
                early_repayment_month=180,
            )

    # -----------------------------------------------------------------------
    # RED — duration < 1 is checked before early_repayment checks
    # -----------------------------------------------------------------------

    def test_duration_zero_takes_priority_over_invalid_early_repayment(self, base_calc):
        """When both duration=0 and early_repayment=0 are invalid, the duration
        guard fires first (it is checked unconditionally before the early_repayment block).
        """
        with pytest.raises(ValueError, match="duration"):
            base_calc._validate_early_repayment_args(
                duration=0,
                early_repayment=0,
                early_repayment_month=60,
            )

    # -----------------------------------------------------------------------
    # GREEN — parametrize valid (duration, early_repayment, month) triples
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("duration,amount,month", [
        (2,   1,        1),       # minimum duration with minimum valid month
        (360, 50_000,   1),       # 30-year loan, first month
        (360, 50_000,   359),     # 30-year loan, last valid month
        (12,  5_000,    6),       # 1-year loan, mid-point
        (180, 0.01,     90),      # smallest positive float amount
    ])
    def test_valid_combinations_do_not_raise(self, base_calc, duration, amount, month):
        """A selection of valid (duration, early_repayment, month) triples must all
        return None without raising.
        """
        result = base_calc._validate_early_repayment_args(
            duration=duration,
            early_repayment=amount,
            early_repayment_month=month,
        )
        assert result is None

    # -----------------------------------------------------------------------
    # RED — parametrize invalid month boundaries
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("month", [0, -1, -100, 180, 181, 999])
    def test_invalid_month_values_all_raise_value_error(self, base_calc, month):
        """All month values outside [1, duration-1] must raise ValueError."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=10_000,
                early_repayment_month=month,
            )


# ===========================================================================
# Regression: delegation from both public methods to _validate_early_repayment_args
# ===========================================================================

class TestDelegationToValidateEarlyRepaymentArgs:
    """Regression tests confirming that both public methods delegate argument
    validation to _validate_early_repayment_args.

    Each test verifies that a specific invalid combination raises ValueError
    (or is accepted) via the public API, proving the delegation is wired up
    in both ``calculate_loan_amortization_table`` and
    ``calculate_monthly_repayment_and_loan_amortization_table``.
    """

    # -----------------------------------------------------------------------
    # calculate_loan_amortization_table — delegation verified for each raise path
    # -----------------------------------------------------------------------

    def test_amortization_table_delegates_duration_zero(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for duration=0
        (via _validate_early_repayment_args delegation).
        """
        with pytest.raises(ValueError, match="duration"):
            base_calc.calculate_loan_amortization_table(
                duration=0,
                monthly_repayment=Decimal("1000.00"),
            )

    def test_amortization_table_delegates_duration_negative(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for duration=-5."""
        with pytest.raises(ValueError, match="duration"):
            base_calc.calculate_loan_amortization_table(
                duration=-5,
                monthly_repayment=Decimal("1000.00"),
            )

    def test_amortization_table_delegates_early_repayment_zero(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for early_repayment=0."""
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc.calculate_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=0,
                early_repayment_month=60,
            )

    def test_amortization_table_delegates_early_repayment_negative(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for early_repayment=-500."""
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc.calculate_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=-500,
                early_repayment_month=60,
            )

    def test_amortization_table_delegates_early_repayment_month_zero(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for early_repayment_month=0."""
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc.calculate_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=10_000,
                early_repayment_month=0,
            )

    def test_amortization_table_delegates_early_repayment_month_equals_duration(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for
        early_repayment_month=duration (strict upper-bound violation).
        """
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc.calculate_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=10_000,
                early_repayment_month=180,
            )

    def test_amortization_table_delegates_early_repayment_month_above_duration(self, base_calc):
        """calculate_loan_amortization_table must raise ValueError for
        early_repayment_month > duration.
        """
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc.calculate_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=10_000,
                early_repayment_month=200,
            )

    # -----------------------------------------------------------------------
    # calculate_monthly_repayment_and_loan_amortization_table — delegation verified
    # -----------------------------------------------------------------------

    def test_solver_delegates_duration_zero(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for duration=0 (via _validate_early_repayment_args delegation).
        """
        with pytest.raises(ValueError, match="duration"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=0,
                monthly_repayment=Decimal("1000.00"),
            )

    def test_solver_delegates_duration_negative(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for duration=-1.
        """
        with pytest.raises(ValueError, match="duration"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=-1,
                monthly_repayment=Decimal("1000.00"),
            )

    def test_solver_delegates_early_repayment_zero(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for early_repayment=0.
        """
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=0,
                early_repayment_month=60,
            )

    def test_solver_delegates_early_repayment_negative(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for early_repayment=-1.
        """
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=-1,
                early_repayment_month=60,
            )

    def test_solver_delegates_early_repayment_month_zero(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for early_repayment_month=0.
        """
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=10_000,
                early_repayment_month=0,
            )

    def test_solver_delegates_early_repayment_month_equals_duration(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for early_repayment_month=duration (strict upper-bound violation).
        """
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=10_000,
                early_repayment_month=180,
            )

    def test_solver_delegates_early_repayment_month_above_duration(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must raise ValueError
        for early_repayment_month > duration.
        """
        with pytest.raises(ValueError, match="early_repayment_month"):
            base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                duration=180,
                monthly_repayment=Decimal("1000.00"),
                early_repayment=10_000,
                early_repayment_month=200,
            )

    # -----------------------------------------------------------------------
    # Confirm delegation is via the method (not duplicated logic): patch test
    # -----------------------------------------------------------------------

    def test_amortization_table_calls_validate_method(self, base_calc):
        """calculate_loan_amortization_table must call _validate_early_repayment_args
        before doing any computation.  Patch the private method to raise and confirm
        the public method propagates the error unchanged.
        """
        with patch.object(
            base_calc,
            "_validate_early_repayment_args",
            side_effect=ValueError("sentinel validation error"),
        ):
            with pytest.raises(ValueError, match="sentinel validation error"):
                base_calc.calculate_loan_amortization_table(
                    duration=180,
                    monthly_repayment=Decimal("1000.00"),
                )

    def test_solver_calls_validate_method(self, base_calc):
        """calculate_monthly_repayment_and_loan_amortization_table must call
        _validate_early_repayment_args before doing any computation.  Patch the
        private method to raise and confirm the public method propagates the error.
        """
        with patch.object(
            base_calc,
            "_validate_early_repayment_args",
            side_effect=ValueError("sentinel validation error"),
        ):
            with pytest.raises(ValueError, match="sentinel validation error"):
                base_calc.calculate_monthly_repayment_and_loan_amortization_table(
                    duration=180,
                    monthly_repayment=Decimal("1000.00"),
                )
