"""Tests for loan_calculator.py — LoanCalculator.

Green tests verify correct, expected behaviour.
Red (xfail / skip) tests document known gaps: inputs the class does not guard
against, non-deterministic code paths, and bugs where list-valued insurance
parameters are not converted to Decimal.
"""

import pytest
from decimal import Decimal

from loan_calculator import LoanCalculator


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

    # -----------------------------------------------------------------------
    # RED — known gaps (xfail)
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # RED — known gaps (xfail)
    # -----------------------------------------------------------------------

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
    # GREEN — termination behaviour
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


# ===========================================================================
# calculate_monthly_repayment_and_loan_amortization_table
# ===========================================================================

class TestCalculateMonthlyRepaymentAndLoanAmortizationTable:
    """Tests for LoanCalculator.calculate_monthly_repayment_and_loan_amortization_table.

    Only the two deterministic paths are tested:
    - Case 1: no early repayment, correct repayment passed as starting estimate
              → solver returns immediately with the passed-through value.
    - Case 2: early repayment provided → solver converges and table ends before duration.

    The stochastic fallback (np.random.random()) is documented via a skip stub.
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
        """Case 2: early repayment makes the loan finish before month 180."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["month"][-1] < DURATION

    def test_case2_returned_monthly_repayment_is_decimal(self, calc_single):
        """Case 2: solver returns a Decimal monthly repayment."""
        _, monthly = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert isinstance(monthly, Decimal)

    def test_case2_table_ends_at_month_131(self, calc_single):
        """Case 2: 690/month + 20000 early repayment at month 60 ends at month 131."""
        table, _ = calc_single.calculate_monthly_repayment_and_loan_amortization_table(
            duration=DURATION,
            monthly_repayment=REPAYMENT_HIGH,
            early_repayment=20_000,
            early_repayment_month=60,
        )
        assert table["month"][-1] == 131

    # -----------------------------------------------------------------------
    # RED — stochastic fallback not tested (skip stub)
    # -----------------------------------------------------------------------

    @pytest.mark.skip(
        reason=(
            "Case 3 / stochastic fallback: the solver uses np.random.random() when "
            "it stalls with capital_ratio==0 and no early repayment. This path is "
            "non-deterministic and cannot be reliably asserted without mocking numpy's "
            "random generator. Covered separately if a seed-fixture approach is added."
        )
    )
    def test_stochastic_fallback_not_tested(self, calc_single):
        """Stub: documents that the random-fallback branch is intentionally untested."""
        pass
