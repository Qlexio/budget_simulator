import numpy as np
import pandas as pd
from decimal import Decimal as _Decimal
from typing import Optional, Union, cast
from collections.abc import Sequence
from ._utils import quantize_amount, to_decimal


class LoanCalculator():
    """_summary_
    """
    def __init__(self, loan_amount: Union[int, float], annual_interest_rate: Union[int, float], annual_insurance_rate: Union[int, float, list[Union[int, float]]],
                 monthly_repayment: Union[int, float] = 0, insured_number: int = 1, insurance_coverage: Union[float, int, list[Union[int, float]]] = 1):
        """_summary_

        Args:
            loan_amount (Union[int, float]): _description_
            annual_interest_rate (Union[int, float]): _description_
            annual_insurance_rate (Union[int, float, list[Union[int, float]]]): _description_
            monthly_repayment (Union[int, float], optional): _description_. Defaults to 0.
            insured_number (int, optional): _description_. Defaults to 1.
            insurance_coverage (Union[float, int, list[Union[int, float]]], optional): _description_. Defaults to 1.
        """
        # TODO Docstring
        self.loan_amount = to_decimal(loan_amount)
        self.annual_interest_rate = to_decimal(annual_interest_rate, precision="0.00001")

        self.insured_number = insured_number  # TODO To quantize?
        # Insurance Rate, e.g. x%
        self.annual_insurance_rate = self._format_insurance_related_values(annual_insurance_rate, precision="0.00001")
        # Insurance coverage, e.g. 50% or 100% of the total insurance coverage from 0% to 100%
        self.insurance_coverage = self._format_insurance_related_values(cast(Union[int, float], insurance_coverage))

        self.monthly_repayment = to_decimal(monthly_repayment)
        self.loan_amortization_table = None

    def _format_insurance_related_values(self, insurance_value: Union[int, float, list[Union[int, float]]], 
                                         insured_number: Optional[int] = None, precision: str = "0.01") -> list[_Decimal]:
        """_summary_

        Args:
            insurance_value (Union[int, float, list[Union[int, float]]]): _description_
            insured_number (Optional[int], optional): _description_. Defaults to None.
            precision (str, optional): _description_. Defaults to "0.01".

        Returns:
            list[_Decimal]: _description_
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
                ret_insurance_value.append(ins_value)
            return ret_insurance_value
        return []

    def validate_refunded_capital(self, monthly_repayment: _Decimal, insurance_N1: _Decimal, remaining_capital: _Decimal, annual_interest_rate: _Decimal,
                                  capital_tolerance: Union[int, float, _Decimal]=0.1) -> tuple[_Decimal, _Decimal, _Decimal]:
        """_summary_

        Args:
            monthly_repayment (_Decimal): _description_
            insurance_N1 (_Decimal): _description_
            remaining_capital (_Decimal): _description_
            annual_interest_rate (_Decimal): _description_
            capital_tolerance (Union[int, float, _Decimal], optional): _description_. Defaults to 0.1.

        Returns:
            tuple[_Decimal, _Decimal, _Decimal]: _description_
        """
        # TODO Docstring + translation
        tolerance = _Decimal(capital_tolerance).quantize(_Decimal("0.00001"))

        interest = remaining_capital * annual_interest_rate / 12
        current_refunded_capital = monthly_repayment - interest - insurance_N1
        refunded_capital_difference = remaining_capital - current_refunded_capital
        if refunded_capital_difference < monthly_repayment * tolerance:
            current_refunded_capital = remaining_capital
            current_remaining_capital = 0
        else:
            current_remaining_capital = remaining_capital - current_refunded_capital
        return interest, current_refunded_capital, _Decimal(current_remaining_capital)

    def calculated_monthly_insurance(self, remaining_capital: _Decimal) -> _Decimal:
        """_summary_

        Args:
            remaining_capital (_Decimal): _description_

        Returns:
            _Decimal: _description_
        """
        # TODO Docstring + translation
        monthly_insurance_cost = to_decimal(0)
        for annual_rate, coverage in zip(self.annual_insurance_rate, self.insurance_coverage):
            monthly_insurance_cost += remaining_capital * ((annual_rate * coverage) / 12)
        return monthly_insurance_cost

    def calculate_loan_amortization_table(self, duration: int, initial_loan_amount: _Decimal, annual_interest_rate: _Decimal,
                                          monthly_repayment: _Decimal,
                                          early_repayment: Optional[Union[int, float]] = None, early_repayment_month: int = 0, 
                                          capital_tolerance: Union[int, float] = 0.1) -> dict[str, Union[_Decimal, int]]:
        """_summary_

        Args:
            duration (int): _description_
            initial_loan_amount (_Decimal): _description_
            annual_interest_rate (_Decimal): _description_
            monthly_repayment (_Decimal): _description_
            early_repayment (Optional[Union[int, float]], optional): _description_. Defaults to None.
            early_repayment_month (int, optional): _description_. Defaults to 0.
            capital_tolerance (Union[int, float], optional): _description_. Defaults to 0.1.

        Returns:
            dict[str, Union[_Decimal, int]]: _description_
        """
        # TODO Docstring
        loan_amortization_table = {"month": [1], "interest": None, "insurance": None, "refunded_capital": None, "remaining_capital": None, "cumulated_costs": None}

        loan_amortization_table["interest"] = [quantize_amount(initial_loan_amount * annual_interest_rate / 12)]
        loan_amortization_table["insurance"] = [quantize_amount(self.calculated_monthly_insurance(remaining_capital=initial_loan_amount))]
        loan_amortization_table["refunded_capital"] = [quantize_amount(monthly_repayment - loan_amortization_table["interest"][-1] - loan_amortization_table["insurance"][-1])]
        loan_amortization_table["remaining_capital"] = [quantize_amount(initial_loan_amount - loan_amortization_table["refunded_capital"][-1])]
        loan_amortization_table["cumulated_costs"] = [quantize_amount(loan_amortization_table["interest"][-1] + loan_amortization_table["insurance"][-1])]

        for i in range(1, duration):
            loan_amortization_table["month"].append(i + 1)
            if early_repayment is not None:
                decimal_early_repayment = to_decimal(early_repayment)
            else:
                decimal_early_repayment = to_decimal(0)
            remaining_capital = loan_amortization_table["remaining_capital"][-1] - decimal_early_repayment if early_repayment_month == i else loan_amortization_table["remaining_capital"][-1]
            
            loan_amortization_table["insurance"].append(quantize_amount(self.calculated_monthly_insurance(remaining_capital=remaining_capital)))
            
            interest, current_refunded_capital, current_remaining_capital = self.validate_refunded_capital(monthly_repayment=monthly_repayment, insurance_N1=loan_amortization_table["insurance"][-1],
                                    remaining_capital=remaining_capital, annual_interest_rate=annual_interest_rate, capital_tolerance=capital_tolerance)
            loan_amortization_table["interest"].append(quantize_amount(interest))
            loan_amortization_table["refunded_capital"].append(quantize_amount(current_refunded_capital))
            loan_amortization_table["remaining_capital"].append(quantize_amount(current_remaining_capital))
            loan_amortization_table["cumulated_costs"].append(loan_amortization_table["cumulated_costs"][-1] + loan_amortization_table["interest"][-1] + loan_amortization_table["insurance"][-1])

            if loan_amortization_table["remaining_capital"][-1] <= 0:
                break

        return loan_amortization_table
