import numpy as np
from decimal import Decimal as _Decimal
from typing import Optional, Union, cast
from _utils import quantize_amount, to_decimal


class LoanCalculator:
    """Fixed-rate French mortgage amortization calculator.

    Builds month-by-month amortization tables and can iteratively solve
    for the monthly repayment that exactly amortizes a loan over a given
    duration. Supports one-time early repayments and multi-person insurance.
    """

    def __init__(
        self,
        loan_amount: Union[int, float],
        annual_interest_rate: Union[int, float],
        annual_insurance_rate: Union[int, float, list[Union[int, float]]],
        monthly_repayment: Union[int, float] = 0,
        insured_number: int = 1,
        insurance_coverage: Union[float, int, list[Union[int, float]]] = 1,
    ):
        """Initialise a LoanCalculator for a fixed-rate French mortgage.

        Insurance parameters are normalised to ``list[Decimal]`` at construction
        time via ``_format_insurance_related_values``, supporting one or two
        insured persons with independent rates and coverage ratios.

        Args:
            loan_amount: Total loan principal (int or float; stored as Decimal).
            annual_interest_rate: Nominal annual interest rate as a decimal
                fraction (e.g. 0.015 for 1.5 %).
            annual_insurance_rate: Annual insurance rate(s) as a decimal fraction.
                Pass a single value or a list for multiple insured persons.
            monthly_repayment: Optional known monthly repayment. Defaults to 0
                (use ``calculate_monthly_repayment_and_loan_amortization_table``
                to solve for it).
            insured_number: Number of insured persons (1 or 2). Defaults to 1.
            insurance_coverage: Coverage ratio(s) per insured person (0–1).
                Pass a single value or a list. Defaults to 1 (full coverage).
        """
        self.loan_amount = to_decimal(loan_amount)
        self.annual_interest_rate = to_decimal(annual_interest_rate, precision="0.00001")

        self.insured_number = insured_number
        self.annual_insurance_rate = self._format_insurance_related_values(annual_insurance_rate, precision="0.00001")
        self.insurance_coverage = self._format_insurance_related_values(cast(Union[int, float], insurance_coverage))

        self.monthly_repayment = to_decimal(monthly_repayment)
        self.loan_amortization_table = None

    def _format_insurance_related_values(
        self,
        insurance_value: Union[int, float, list[Union[int, float]]],
        insured_number: Optional[int] = None,
        precision: str = "0.01",
    ) -> list[_Decimal]:
        """Normalise an insurance-related parameter into a ``list[Decimal]``.

        Handles the following cases:
        - Single insured person, scalar input → ``[Decimal(value)]``
        - Single insured person, list input → ``[Decimal(value[0])]``
        - Multiple insured persons, scalar input → ``[value] * insured_number``
        - Multiple insured persons, list input → first ``insured_number`` elements

        Args:
            insurance_value: A scalar (int/float) or list of scalars.
            insured_number: Override for the number of insured persons.
                Defaults to ``self.insured_number``.
            precision: Quantization precision string. Defaults to ``"0.01"``.

        Returns:
            A list of Decimal values, one per insured person.
        """
        if isinstance(insurance_value, (int, float)):
            decimal_insurance_value = to_decimal(insurance_value, precision=precision)
        else:
            decimal_insurance_value = insurance_value
        if not insured_number:
            insured_number = self.insured_number
        if insured_number == 1 and not isinstance(decimal_insurance_value, list):
            return [decimal_insurance_value]
        if isinstance(decimal_insurance_value, list) and insured_number == 1:
            return [to_decimal(decimal_insurance_value[0], precision=precision)]
        if insured_number > 1 and not isinstance(decimal_insurance_value, list):
            ret_insurance_value = []
            for i in range(self.insured_number):
                ret_insurance_value.append(decimal_insurance_value)
            return ret_insurance_value
        if insured_number > 1 and isinstance(decimal_insurance_value, list):
            ret_insurance_value = []
            for _, ins_value in zip(range(insured_number), decimal_insurance_value):
                ret_insurance_value.append(to_decimal(ins_value, precision=precision))
            return ret_insurance_value
        return []

    def _compute_payment_breakdown(
        self,
        monthly_repayment: _Decimal,
        monthly_insurance: _Decimal,
        remaining_capital: _Decimal,
        capital_tolerance: Union[int, float, _Decimal] = 0.1,
    ) -> tuple[_Decimal, _Decimal, _Decimal]:
        """Decompose a single monthly payment into interest, principal, and remaining balance.

        Applies a tolerance check: if the remaining difference would be less than
        ``monthly_repayment * capital_tolerance``, the entire remaining balance is
        treated as repaid in this period (avoids a rounding-driven final micro-payment).

        Uses ``self.annual_interest_rate`` internally.

        Args:
            monthly_repayment: The fixed monthly payment amount.
            monthly_insurance: The monthly insurance cost for this period.
            remaining_capital: The outstanding loan balance before this payment.
            capital_tolerance: Fraction of monthly_repayment used as the
                end-of-loan tolerance threshold. Accepts int, float, or Decimal.
                Defaults to 0.1.

        Returns:
            A 3-tuple of (interest, repaid_capital, remaining_capital), all Decimal.
        """
        tolerance = to_decimal(float(capital_tolerance), precision="0.00001")

        interest = remaining_capital * self.annual_interest_rate / 12
        current_refunded_capital = monthly_repayment - interest - monthly_insurance
        refunded_capital_difference = remaining_capital - current_refunded_capital
        if refunded_capital_difference < monthly_repayment * tolerance:
            current_refunded_capital = remaining_capital
            current_remaining_capital = _Decimal("0")
        else:
            current_remaining_capital = remaining_capital - current_refunded_capital
        return interest, current_refunded_capital, current_remaining_capital

    def _compute_monthly_insurance(self, remaining_capital: _Decimal) -> _Decimal:
        """Compute the total monthly insurance cost across all insured persons.

        For each insured person, the monthly cost is:
            remaining_capital * (annual_rate * coverage) / 12

        Args:
            remaining_capital: The outstanding loan balance for this month.

        Returns:
            The total monthly insurance premium as an unquantized Decimal
            (caller is responsible for final quantization via quantize_amount).
        """
        monthly_insurance_cost = _Decimal("0")
        for annual_rate, coverage in zip(self.annual_insurance_rate, self.insurance_coverage):
            monthly_insurance_cost += remaining_capital * ((annual_rate * coverage) / 12)
        return monthly_insurance_cost

    def calculate_loan_amortization_table(
        self,
        duration: int,
        monthly_repayment: _Decimal,
        early_repayment: Optional[Union[int, float]] = None,
        early_repayment_month: int = 0,
        capital_tolerance: Union[int, float] = 0.1,
    ) -> dict[str, list[Union[_Decimal, int]]]:
        """Build a month-by-month loan amortization table.

        Starting from ``self.loan_amount`` and iterating for up to ``duration``
        months, each row records the interest paid, insurance cost, capital repaid,
        outstanding balance, and cumulative total cost. The loop terminates early
        once the remaining capital reaches zero.

        An optional one-time early repayment is applied at ``early_repayment_month``
        by subtracting ``early_repayment`` from the outstanding balance before
        computing that month's insurance and payment breakdown.

        Args:
            duration: Maximum number of monthly periods.
            monthly_repayment: Fixed monthly payment amount.
            early_repayment: Optional lump-sum early repayment amount.
            early_repayment_month: The month index (1-based) at which the early
                repayment occurs. Ignored when ``early_repayment`` is None.
            capital_tolerance: Fraction of monthly_repayment used as the
                end-of-loan tolerance threshold. Defaults to 0.1.

        Returns:
            A dict with keys ``month``, ``interest``, ``insurance``,
            ``refunded_capital``, ``remaining_capital``, ``cumulated_costs``,
            each mapping to a list of Decimal (or int for ``month``).
        """
        month1_interest = quantize_amount(self.loan_amount * self.annual_interest_rate / 12)
        month1_insurance = quantize_amount(self._compute_monthly_insurance(remaining_capital=self.loan_amount))
        month1_refunded = quantize_amount(monthly_repayment - month1_interest - month1_insurance)
        loan_amortization_table = {
            "month": [1],
            "interest": [month1_interest],
            "insurance": [month1_insurance],
            "refunded_capital": [month1_refunded],
            "remaining_capital": [quantize_amount(self.loan_amount - month1_refunded)],
            "cumulated_costs": [quantize_amount(month1_interest + month1_insurance)],
        }

        decimal_early_repayment = to_decimal(early_repayment) if early_repayment is not None else _Decimal("0")

        for i in range(1, duration):
            loan_amortization_table["month"].append(i + 1)
            remaining_capital = (
                loan_amortization_table["remaining_capital"][-1] - decimal_early_repayment
                if early_repayment_month == i
                else loan_amortization_table["remaining_capital"][-1]
            )

            loan_amortization_table["insurance"].append(quantize_amount(self._compute_monthly_insurance(remaining_capital=remaining_capital)))

            interest, current_refunded_capital, current_remaining_capital = self._compute_payment_breakdown(
                monthly_repayment=monthly_repayment,
                monthly_insurance=loan_amortization_table["insurance"][-1],
                remaining_capital=remaining_capital,
                capital_tolerance=capital_tolerance,
            )
            loan_amortization_table["interest"].append(quantize_amount(interest))
            loan_amortization_table["refunded_capital"].append(quantize_amount(current_refunded_capital))
            loan_amortization_table["remaining_capital"].append(quantize_amount(current_remaining_capital))
            loan_amortization_table["cumulated_costs"].append(
                loan_amortization_table["cumulated_costs"][-1]
                + loan_amortization_table["interest"][-1]
                + loan_amortization_table["insurance"][-1]
            )

            if loan_amortization_table["remaining_capital"][-1] <= 0:
                break

        return loan_amortization_table

    def calculate_monthly_repayment_and_loan_amortization_table(
        self,
        duration: int,
        monthly_repayment: _Decimal,
        early_repayment: Optional[Union[int, float]] = None,
        early_repayment_month: int = 0,
        capital_tolerance: Union[int, float] = 0.1,
    ) -> tuple[dict[str, list[Union[_Decimal, int]]], _Decimal]:
        """Iteratively solve for the monthly repayment that exactly amortizes the loan
        over ``duration`` months, then return the final amortization table.

        Uses a capital-ratio heuristic to adjust ``monthly_repayment`` upward or
        downward each iteration until the amortization table ends at zero remaining
        capital on exactly month ``duration`` (or earlier when ``early_repayment``
        is provided). Falls back to a random negative capital ratio if the solver
        stalls.

        Note:
            The random fallback makes this method non-deterministic when it stalls.

        Args:
            duration: Target loan duration in months.
            monthly_repayment: Starting monthly repayment estimate.
            early_repayment: Optional lump-sum early repayment amount.
            early_repayment_month: Month index for the early repayment.
            capital_tolerance: End-of-loan tolerance fraction. Defaults to 0.1.

        Returns:
            A 2-tuple of (amortization_table dict, final monthly_repayment Decimal).
        """
        # TODO To a look in case of early repayment calculation as the monthly repayment should stay the same but duration change.

        loan_amortization_table = self.calculate_loan_amortization_table(
            duration=duration,
            monthly_repayment=monthly_repayment,
            early_repayment=early_repayment,
            early_repayment_month=early_repayment_month,
            capital_tolerance=capital_tolerance,
        )

        def calculate_new_monthly_repayment(monthly_repayment, current_remaining_capital, loan_amount, initial_capital_ratio=None):
            capital_ratio = initial_capital_ratio or current_remaining_capital / loan_amount
            capital_ratio = to_decimal(capital_ratio, precision="0.000001")
            return quantize_amount(monthly_repayment * (1 + (capital_ratio / 2))), capital_ratio

        if all((loan_amortization_table["remaining_capital"][-1] == 0, loan_amortization_table["remaining_capital"][-2] != 0)):
            return loan_amortization_table, monthly_repayment

        new_monthly_repayment = monthly_repayment
        new_monthly_repayment_list = []
        capital_ratio = None

        while True:
            new_monthly_repayment, capital_ratio = calculate_new_monthly_repayment(
                new_monthly_repayment,
                loan_amortization_table["remaining_capital"][-1],
                self.loan_amount,
                initial_capital_ratio=capital_ratio,
            )
            loan_amortization_table = self.calculate_loan_amortization_table(
                duration=duration,
                monthly_repayment=new_monthly_repayment,
                early_repayment=early_repayment,
                early_repayment_month=early_repayment_month,
                capital_tolerance=capital_tolerance,
            )

            if len(new_monthly_repayment_list) < 10:
                new_monthly_repayment_list.append(new_monthly_repayment)
            else:
                new_monthly_repayment_list.pop(0)
                new_monthly_repayment_list.append(new_monthly_repayment)

            # Case 1: No early repayment — should end at duration
            if all((
                loan_amortization_table["remaining_capital"][-1] == 0,
                loan_amortization_table["remaining_capital"][-2] != 0,
                early_repayment is None,
                loan_amortization_table["month"][-1] == duration,
            )):
                return loan_amortization_table, new_monthly_repayment
            # Case 2: Early repayment — can end earlier
            elif all((
                loan_amortization_table["remaining_capital"][-1] == 0,
                loan_amortization_table["remaining_capital"][-2] != 0,
                early_repayment is not None,
            )):
                return loan_amortization_table, new_monthly_repayment
            # Case 3: End too early and/or solver stalled — reset with random ratio
            elif all((
                loan_amortization_table["remaining_capital"][-1] == 0,
                capital_ratio == 0,
                early_repayment is None,
            )):
                capital_ratio = -np.random.random()
            # Case 4: Other cases — reset capital ratio
            else:
                capital_ratio = None
