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
    """Tests for LoanCalculator._format_insurance_related_values and __init__ validation."""

    # -- __init__ guards --

    def test_init_loan_amount_zero_raises_value_error(self):
        """loan_amount=0 is at the boundary (not positive) and must raise ValueError."""
        with pytest.raises(ValueError, match="loan_amount"):
            LoanCalculator(loan_amount=0, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE)

    def test_init_loan_amount_one_does_not_raise(self):
        """loan_amount=1 is at the positive boundary and must not raise."""
        calc = LoanCalculator(loan_amount=1, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE)
        assert calc.loan_amount == Decimal("1.00")

    def test_init_negative_interest_rate_raises_value_error(self):
        """annual_interest_rate < 0 must raise ValueError."""
        with pytest.raises(ValueError, match="annual_interest_rate"):
            LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=-0.001, annual_insurance_rate=INSURANCE_RATE)

    def test_init_zero_interest_rate_does_not_raise(self):
        """annual_interest_rate=0 (interest-free loan) is valid and must not raise."""
        calc = LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=0, annual_insurance_rate=INSURANCE_RATE)
        assert calc.annual_interest_rate == Decimal("0.00000")

    def test_init_insured_number_zero_raises_value_error(self):
        """insured_number=0 violates the >= 1 constraint."""
        with pytest.raises(ValueError, match="insured_number"):
            LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE, insured_number=0)

    def test_init_insured_number_float_raises_value_error(self):
        """insured_number=1.0 is a float, not int, and must raise ValueError."""
        with pytest.raises(ValueError, match="insured_number"):
            LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE, insured_number=1.0)  # type: ignore[arg-type]

    def test_init_negative_insurance_rate_raises_value_error(self):
        """annual_insurance_rate < 0 must raise ValueError."""
        with pytest.raises(ValueError, match="annual_insurance_rate"):
            LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=-0.001)

    def test_init_insurance_coverage_above_one_raises_value_error(self):
        """insurance_coverage > 1 must raise ValueError."""
        with pytest.raises(ValueError, match="insurance_coverage"):
            LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE, insurance_coverage=1.1)

    def test_init_insurance_coverage_zero_does_not_raise(self):
        """insurance_coverage=0 is at the lower boundary and must not raise."""
        calc = LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE, insurance_coverage=0)
        assert calc.insurance_coverage[0] == Decimal("0.00")

    def test_init_insurance_coverage_one_does_not_raise(self):
        """insurance_coverage=1 is at the upper boundary and must not raise."""
        calc = LoanCalculator(loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE, annual_insurance_rate=INSURANCE_RATE, insurance_coverage=1)
        assert calc.insurance_coverage[0] == Decimal("1.00")

    # -- _format_insurance_related_values: one test per branch --
    #
    # Branch map:
    #   B1  insured_number == 1, scalar input  → [Decimal(value)]
    #   B2  insured_number == 1, list input    → [Decimal(list[0])]
    #   B3  insured_number > 1, scalar input   → [value] * n
    #   B4  insured_number > 1, list len == 1  → broadcast to n elements (no warning)
    #   B5  insured_number > 1, list len == n  → values preserved in order
    #   B6  insured_number > 1, list len > n   → UserWarning + first n elements kept
    # Error: insured_number > 1, list len > 1 and len < n → ValueError

    def test_b1_scalar_insured1_value_matches_input(self, calc_single):
        """B1: scalar + insured_number=1 → [Decimal(value)] at the given precision."""
        result = calc_single._format_insurance_related_values(0.5, insured_number=1, precision="0.01")
        assert result == [Decimal("0.50")]

    def test_b2_list_insured1_uses_first_element_only(self, calc_single):
        """B2: list + insured_number=1 → only the first element is kept; extras silently dropped."""
        result = calc_single._format_insurance_related_values(
            [0.003, 0.007, 0.009], insured_number=1, precision="0.00001"
        )
        assert len(result) == 1
        assert result[0] == Decimal("0.00300")

    def test_b3_scalar_insured2_broadcasts_value(self):
        """B3: scalar + insured_number=2 → two equal Decimal copies of the input."""
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT, annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE, insured_number=2,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=2, precision="0.00001")
        assert len(result) == 2
        assert result[0] == result[1] == Decimal("0.00300")

    def test_b4_list_of_one_broadcasts_without_warning(self, calc_single):
        """B4: length-1 list + insured_number=2 → broadcast to 2 elements, no UserWarning."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning becomes an error
            result = calc_single._format_insurance_related_values([0.5], insured_number=2, precision="0.01")
        assert result[0] == result[1] == Decimal("0.50")

    def test_b5_exact_list_preserves_values_and_order(self, calc_single):
        """B5: list len == insured_number → all values kept, original order preserved."""
        result = calc_single._format_insurance_related_values(
            [0.009, 0.001], insured_number=2, precision="0.00001"
        )
        assert result[0] == Decimal("0.00900")
        assert result[1] == Decimal("0.00100")

    def test_b6_longer_list_warns_and_truncates(self, calc_single):
        """B6: list len > insured_number → UserWarning emitted, first n elements kept."""
        with pytest.warns(UserWarning, match="extra values will be ignored"):
            result = calc_single._format_insurance_related_values(
                [0.001, 0.003, 0.005], insured_number=2, precision="0.00001"
            )
        assert len(result) == 2
        assert result[0] == Decimal("0.00100")
        assert result[1] == Decimal("0.00300")

    def test_shorter_list_than_insured_number_raises_value_error(self, calc_single):
        """list len > 1 and len < insured_number → ValueError mentioning 'less than'."""
        with pytest.raises(ValueError, match="less than"):
            calc_single._format_insurance_related_values(
                [0.002, 0.004], insured_number=3, precision="0.00001"
            )

    def test_b3_scalar_override_insured_number_differs_from_self(self):
        """Fix 1: scalar + override insured_number=2 on a insured_number=1 instance.

        Before Fix 1, _format_insurance_related_values used self.insured_number (1)
        in the scalar-expansion loop, so the returned list had only 1 element.
        After the fix, the local parameter is respected and the list has length 2.
        """
        calc = LoanCalculator(
            loan_amount=LOAN_AMOUNT,
            annual_interest_rate=ANNUAL_RATE,
            annual_insurance_rate=INSURANCE_RATE,
            insured_number=1,
        )
        result = calc._format_insurance_related_values(0.003, insured_number=2, precision="0.00001")
        assert len(result) == 2
        assert result[0] == result[1] == Decimal("0.00300")

    def test_init_negative_monthly_repayment_raises_value_error(self):
        """Fix 3: monthly_repayment < 0 must raise ValueError mentioning 'monthly_repayment'."""
        with pytest.raises(ValueError, match="monthly_repayment"):
            LoanCalculator(
                loan_amount=LOAN_AMOUNT,
                annual_interest_rate=ANNUAL_RATE,
                annual_insurance_rate=INSURANCE_RATE,
                monthly_repayment=-1,
            )


# ===========================================================================
# _compute_payment_breakdown
# ===========================================================================

class TestComputePaymentBreakdown:
    """Tests for LoanCalculator._compute_payment_breakdown."""

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
        """When difference < tolerance threshold, repaid_capital is capped at remaining and new_remaining is zero."""
        # remaining=100 << repayment=690; cap fires because 100−repaid < 690×0.1=69
        _, repaid, new_remaining = calc_single._compute_payment_breakdown(
            monthly_repayment=Decimal("690.00"),
            monthly_insurance=Decimal("25.00"),
            remaining_capital=Decimal("100.00"),
            capital_tolerance=0.1,
        )
        assert repaid == Decimal("100.00")
        assert new_remaining == Decimal("0")


# ===========================================================================
# _compute_monthly_insurance
# ===========================================================================

class TestComputeMonthlyInsurance:
    """Tests for LoanCalculator._compute_monthly_insurance."""

    def test_single_insured_full_coverage_concrete_value(self, calc_single):
        """Spot-check: 100000 × 0.003 / 12 = 25.000…"""
        result = calc_single._compute_monthly_insurance(Decimal("100000.00"))
        assert abs(result - Decimal("25.0")) <= Decimal("0.00001")

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


# ===========================================================================
# calculate_loan_amortization_table
# ===========================================================================

class TestCalculateLoanAmortizationTable:
    """Tests for LoanCalculator.calculate_loan_amortization_table."""

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

    def test_month1_concrete_values(self, calc_single):
        """Month 1 spot-check: all fields match 690 repayment on 100k loan at 1.5%/0.3%."""
        table = calc_single.calculate_loan_amortization_table(
            duration=DURATION, monthly_repayment=REPAYMENT_HIGH
        )
        assert table["month"][0] == 1
        assert table["interest"][0] == Decimal("125.00")        # 100000 × 0.015 / 12
        assert table["insurance"][0] == Decimal("25.00")        # 100000 × 0.003 / 12
        assert table["refunded_capital"][0] == Decimal("540.00")    # 690 − 125 − 25
        assert table["remaining_capital"][0] == Decimal("99460.00")  # 100000 − 540
        assert table["cumulated_costs"][0] == Decimal("150.00")     # 125 + 25

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

    def test_strategy_b_month_sequence_is_contiguous(self, calc_single):
        """Strategy B: all month values form a contiguous sequence 1..DURATION.

        The merged table must contain every integer from 1 to DURATION exactly
        once and in order — no duplicates, no gaps, no off-by-one at the
        Phase 1→Phase 2 boundary (GitHub issue #10).
        """
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["month"] == list(range(1, DURATION + 1))

    def test_duration_one_solver_converges_without_error(self):
        """Fix 2: solver with duration=1 must not raise and must return a zero-balance table.

        Before Fix 2, the fast-exit guard read remaining_capital[-2] via a wrap-around
        index on a length-1 list, hitting the last element again and preventing the
        guard from firing; the solver then entered the loop and raised RuntimeError.

        The repayment is computed as: principal + interest + insurance
            = 100 000 + (100 000 × 0.015 / 12) + (100 000 × 0.003 / 12)
            = 100 000 + 125.00 + 25.00
            = 100 150.00
        This is the exact amount that leaves zero remaining capital after a single month.
        """
        calc = LoanCalculator(
            loan_amount=100_000,
            annual_interest_rate=0.015,
            annual_insurance_rate=0.003,
        )
        table, _ = calc.calculate_monthly_repayment_and_loan_amortization_table(
            duration=1,
            monthly_repayment=Decimal("100150.00"),
        )
        assert len(table["month"]) == 1
        assert table["remaining_capital"][0] == Decimal("0.00")

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

    def test_duration_zero_raises_value_error(self, base_calc):
        """duration=0 is below the minimum of 1; must raise ValueError mentioning 'duration'."""
        with pytest.raises(ValueError, match="duration"):
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

    def test_valid_early_repayment_float_amount_does_not_raise(self, base_calc):
        """A float early_repayment value (e.g. 9999.99) is accepted; must return None."""
        result = base_calc._validate_early_repayment_args(
            duration=180,
            early_repayment=9999.99,
            early_repayment_month=60,
        )
        assert result is None

    def test_early_repayment_zero_raises_value_error(self, base_calc):
        """early_repayment=0 is not positive; must raise ValueError mentioning 'early_repayment'."""
        with pytest.raises(ValueError, match="early_repayment"):
            base_calc._validate_early_repayment_args(
                duration=180,
                early_repayment=0,
                early_repayment_month=60,
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
