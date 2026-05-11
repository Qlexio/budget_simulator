import warnings
from decimal import Decimal as _Decimal
from typing import Optional, Union
from ._utils import quantize_amount, to_decimal


class LoanCalculator:
    """Fixed-rate French mortgage amortization calculator.

    Builds month-by-month amortization tables and can iteratively solve
    for the monthly repayment that exactly amortizes a loan over a given
    duration. Supports one-time early repayments and multi-person insurance.
    """

    # Hard upper bound on solver iterations; prevents infinite loops in pathological
    # cases that neither converge nor trigger the oscillation detector.
    _SOLVER_MAX_ITERATIONS = 1000

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
            insured_number: Number of insured persons (positive integer). Defaults to 1.
            insurance_coverage: Coverage ratio(s) per insured person (0–1).
                Pass a single value or a list. Defaults to 1 (full coverage).
        """
        if loan_amount <= 0:
            raise ValueError(f"loan_amount must be positive, got {loan_amount}")
        if annual_interest_rate < 0:
            raise ValueError(f"annual_interest_rate must be non-negative, got {annual_interest_rate}")
        if not isinstance(insured_number, int) or insured_number < 1:
            raise ValueError(f"insured_number must be a positive integer, got {insured_number}")

        self.loan_amount = to_decimal(loan_amount)
        self.annual_interest_rate = to_decimal(annual_interest_rate, precision="0.00001")

        self.insured_number = insured_number
        self.annual_insurance_rate = self._format_insurance_related_values(annual_insurance_rate, precision="0.00001")
        self.insurance_coverage = self._format_insurance_related_values(insurance_coverage)

        for rate in self.annual_insurance_rate:
            if rate < 0:
                raise ValueError(f"annual_insurance_rate values must be non-negative, got {rate}")
        for cov in self.insurance_coverage:
            if not (_Decimal("0") <= cov <= _Decimal("1")):
                raise ValueError(f"insurance_coverage values must be in [0, 1], got {cov}")

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
            if len(decimal_insurance_value) == 1:
                return [to_decimal(decimal_insurance_value[0], precision=precision)] * insured_number
            if len(decimal_insurance_value) < insured_number:
                raise ValueError(
                    f"insurance list length ({len(decimal_insurance_value)}) is less than "
                    f"insured_number ({insured_number}): cannot determine per-person values"
                )
            if len(decimal_insurance_value) > insured_number:
                warnings.warn(
                    f"insurance list length ({len(decimal_insurance_value)}) exceeds "
                    f"insured_number ({insured_number}): extra values will be ignored",
                    UserWarning,
                    stacklevel=2,
                )
            return [to_decimal(ins_value, precision=precision) for ins_value in decimal_insurance_value[:insured_number]]
        raise AssertionError("unreachable: unhandled insured_number/insurance_value combination")

    def _validate_early_repayment_args(
        self,
        duration: int,
        early_repayment: Optional[Union[int, float]],
        early_repayment_month: int,
    ) -> None:
        """Raise ValueError if early-repayment arguments are invalid.

        Args:
            duration: Loan duration in months (must be >= 1).
            early_repayment: Optional lump-sum amount (must be positive when provided).
            early_repayment_month: 1-based month index (must satisfy 1 <= month < duration).

        Raises:
            ValueError: On any invalid combination of the above arguments.
        """
        if duration < 1:
            raise ValueError(f"duration must be at least 1, got {duration}")
        if early_repayment is not None:
            if early_repayment <= 0:
                raise ValueError(f"early_repayment must be positive, got {early_repayment}")
            if not (1 <= early_repayment_month < duration):
                raise ValueError(
                    f"early_repayment_month must be between 1 and duration-1 ({duration - 1}), "
                    f"got {early_repayment_month}"
                )

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

    def _compute_analytical_monthly_repayment(self, principal: _Decimal, duration: int) -> _Decimal:
        """Compute the monthly repayment that exactly amortizes ``principal`` over ``duration`` months.

        Uses the standard amortization formula with an effective monthly rate that
        folds in insurance (interest + insurance behave identically in the payment breakdown).

        Args:
            principal: Outstanding loan balance to amortize.
            duration: Number of remaining months.

        Returns:
            The monthly repayment quantized to 2 d.p.
        """
        r_eff = (
            float(self.annual_interest_rate)
            + sum(float(r) * float(c) for r, c in zip(self.annual_insurance_rate, self.insurance_coverage))
        ) / 12
        if r_eff == 0:
            monthly = float(principal) / duration
        else:
            monthly = float(principal) * r_eff / (1 - (1 + r_eff) ** (-duration))
        return quantize_amount(to_decimal(monthly))

    def calculate_loan_amortization_table(
        self,
        duration: int,
        monthly_repayment: _Decimal,
        early_repayment: Optional[Union[int, float]] = None,
        early_repayment_month: int = 0,
        capital_tolerance: Union[int, float] = 0.1,
        initial_capital: Optional[_Decimal] = None,
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

        Raises:
            ValueError: If ``duration`` < 1, or if ``early_repayment`` is provided
                with an invalid ``early_repayment_month`` or non-positive amount.
        """
        self._validate_early_repayment_args(duration, early_repayment, early_repayment_month)

        effective_capital = initial_capital if initial_capital is not None else self.loan_amount
        month1_interest = quantize_amount(effective_capital * self.annual_interest_rate / 12)
        month1_insurance = quantize_amount(self._compute_monthly_insurance(remaining_capital=effective_capital))
        month1_refunded = quantize_amount(monthly_repayment - month1_interest - month1_insurance)
        loan_amortization_table = {
            "month": [1],
            "interest": [month1_interest],
            "insurance": [month1_insurance],
            "refunded_capital": [month1_refunded],
            "remaining_capital": [quantize_amount(effective_capital - month1_refunded)],
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

        **No early repayment — iterative solver:**
        Uses a capital-ratio heuristic to adjust ``monthly_repayment`` upward or
        downward each iteration until the amortization table ends at zero remaining
        capital on exactly month ``duration``.

        Each iteration scales the current repayment by ``(1 + capital_ratio / 2)``,
        where ``capital_ratio`` is derived from the residual remaining capital relative
        to the original loan amount. This drives the repayment toward the value that
        exactly exhausts the loan at ``duration``.

        Convergence guard: the solver runs for at most ``self._SOLVER_MAX_ITERATIONS``
        iterations. Oscillation — where the remaining capital alternates between the
        same positive and negative cent-quantized values — is detected and resolved by
        returning the mean of the two bracketing repayments with a ``UserWarning``.
        A ``RuntimeError`` is raised if neither condition is met within the limit.

        **With early repayment — Strategy B (analytical two-phase approach):**
        Phase 1 runs the original repayment from month 1 to ``early_repayment_month``.
        Phase 2 calls ``_compute_analytical_monthly_repayment`` on the reduced principal
        and runs for ``duration - early_repayment_month`` months. The two tables are
        merged into one spanning exactly ``duration`` rows.

        Args:
            duration: Target loan duration in months.
            monthly_repayment: Starting monthly repayment estimate.
            early_repayment: Optional lump-sum early repayment amount.
            early_repayment_month: Month index for the early repayment.
            capital_tolerance: End-of-loan tolerance fraction. Defaults to 0.1.

        Returns:
            A 2-tuple of (amortization_table dict, final monthly_repayment Decimal).

        Raises:
            ValueError: If ``duration`` < 1, or if ``early_repayment`` is provided
                with an invalid ``early_repayment_month`` or non-positive amount.
            RuntimeError: If the iterative solver fails to converge within
                ``self._SOLVER_MAX_ITERATIONS`` iterations without oscillating.
        """
        self._validate_early_repayment_args(duration, early_repayment, early_repayment_month)

        if early_repayment is not None:
            decimal_early_repayment = to_decimal(early_repayment)

            # Phase 1: original repayment for months 1..early_repayment_month
            phase1_table = self.calculate_loan_amortization_table(
                duration=early_repayment_month,
                monthly_repayment=monthly_repayment,
                capital_tolerance=capital_tolerance,
            )

            # Phase 2: solve for a new (lower) repayment over the remaining term
            new_principal = phase1_table["remaining_capital"][-1] - decimal_early_repayment
            remaining_duration = duration - early_repayment_month
            phase2_repayment = self._compute_analytical_monthly_repayment(new_principal, remaining_duration)

            phase2_table = self.calculate_loan_amortization_table(
                duration=remaining_duration,
                monthly_repayment=phase2_repayment,
                initial_capital=new_principal,
                capital_tolerance=capital_tolerance,
            )

            costs_offset = phase1_table["cumulated_costs"][-1]
            merged = {
                "month":             phase1_table["month"] + [m + early_repayment_month for m in phase2_table["month"]],
                "interest":          phase1_table["interest"]         + phase2_table["interest"],
                "insurance":         phase1_table["insurance"]        + phase2_table["insurance"],
                "refunded_capital":  phase1_table["refunded_capital"] + phase2_table["refunded_capital"],
                "remaining_capital": phase1_table["remaining_capital"] + phase2_table["remaining_capital"],
                "cumulated_costs":   phase1_table["cumulated_costs"]  + [c + costs_offset for c in phase2_table["cumulated_costs"]],
            }
            return merged, phase2_repayment

        loan_amortization_table = self.calculate_loan_amortization_table(
            duration=duration,
            monthly_repayment=monthly_repayment,
            capital_tolerance=capital_tolerance,
        )

        def calculate_new_monthly_repayment(monthly_repayment, current_remaining_capital, loan_amount, initial_capital_ratio=None):
            # Use the provided ratio (stall recovery) or derive it from the residual
            # remaining capital relative to the original loan amount. Dividing by 2
            # dampens the correction to avoid overshooting.
            capital_ratio = initial_capital_ratio or current_remaining_capital / loan_amount
            # to_decimal only accepts int/float; convert via float to handle Decimal input
            capital_ratio = to_decimal(float(capital_ratio), precision="0.000001")
            return quantize_amount(monthly_repayment * (1 + (capital_ratio / 2))), capital_ratio

        # Fast exit: initial estimate already converges without iteration
        if all((loan_amortization_table["remaining_capital"][-1] == 0, loan_amortization_table["remaining_capital"][-2] != 0)):
            return loan_amortization_table, monthly_repayment

        new_monthly_repayment = monthly_repayment
        capital_ratio = None

        # last_positive / last_negative track the most recent iteration that left a
        # positive / negative remaining capital, stored as (remaining_capital, repayment).
        # When the same remaining-capital value repeats with the same sign, the solver
        # is cycling: the true solution lies between the two bracketing repayments.
        last_positive: Optional[tuple[_Decimal, _Decimal]] = None
        last_negative: Optional[tuple[_Decimal, _Decimal]] = None

        for _ in range(self._SOLVER_MAX_ITERATIONS):
            new_monthly_repayment, capital_ratio = calculate_new_monthly_repayment(
                new_monthly_repayment,
                loan_amortization_table["remaining_capital"][-1],
                self.loan_amount,
                initial_capital_ratio=capital_ratio,
            )
            loan_amortization_table = self.calculate_loan_amortization_table(
                duration=duration,
                monthly_repayment=new_monthly_repayment,
                capital_tolerance=capital_tolerance,
            )
            current_remaining = loan_amortization_table["remaining_capital"][-1]

            # Case 1: solver converged — table ends exactly at duration
            if all((
                current_remaining == 0,
                loan_amortization_table["remaining_capital"][-2] != 0,
                loan_amortization_table["month"][-1] == duration,
            )):
                return loan_amortization_table, new_monthly_repayment

            # Case 2: oscillation detection — remaining capital alternates between the
            # same positive and negative values (exact Decimal equality at cent precision).
            # A converging sequence (e.g. -100 → +50 → -25) never repeats the same value
            # for a given sign, so this only fires when the solver is truly stuck.
            if current_remaining > 0:
                if last_positive is not None and last_negative is not None and current_remaining == last_positive[0]:
                    # Same positive residual seen again and a negative bracket exists:
                    # solver is cycling. Return the mean of the two bracketing repayments.
                    best_repayment = quantize_amount(
                        (last_negative[1] + last_positive[1]) / 2
                    )
                    warnings.warn(
                        f"Solver oscillating around {best_repayment}; "
                        "returning best-effort result",
                        UserWarning,
                        stacklevel=2,
                    )
                    loan_amortization_table = self.calculate_loan_amortization_table(
                        duration=duration,
                        monthly_repayment=best_repayment,
                        capital_tolerance=capital_tolerance,
                    )
                    return loan_amortization_table, best_repayment
                last_positive = (current_remaining, new_monthly_repayment)

            elif current_remaining < 0:
                if last_negative is not None and last_positive is not None and current_remaining == last_negative[0]:
                    # Same negative residual seen again and a positive bracket exists:
                    # solver is cycling. Return the mean of the two bracketing repayments.
                    best_repayment = quantize_amount(
                        (last_positive[1] + last_negative[1]) / 2
                    )
                    warnings.warn(
                        f"Solver oscillating around {best_repayment}; "
                        "returning best-effort result",
                        UserWarning,
                        stacklevel=2,
                    )
                    loan_amortization_table = self.calculate_loan_amortization_table(
                        duration=duration,
                        monthly_repayment=best_repayment,
                        capital_tolerance=capital_tolerance,
                    )
                    return loan_amortization_table, best_repayment
                last_negative = (current_remaining, new_monthly_repayment)

            # Case 3: loan paid off too early and capital_ratio has bottomed out at zero
            # — inject a fixed negative ratio to push the repayment back down.
            if current_remaining == 0 and capital_ratio == 0:
                capital_ratio = to_decimal("-0.5", precision="0.000001")
            # Case 4: any other non-convergence — clear the ratio so the next iteration
            # re-derives it from the fresh remaining capital.
            else:
                capital_ratio = None

        raise RuntimeError(
            f"Solver did not converge after {self._SOLVER_MAX_ITERATIONS} iterations"
        )
