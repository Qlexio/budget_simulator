import numpy as np
import pandas as pd
from decimal import Decimal as _Decimal
from typing import Optional, Union
from collections.abc import Sequence
from ._utils import quantize_amount, to_decimal


class LoanCalculator():
    """_summary_
    """
    def __init__(self, loan_amount, annual_interest_rate, annual_insurance_rate: Union[int, float, list[Union[int, float]]],
                 monthly_repayment: Union[int, float] = 0, insured_number: int = 1, insurance_coverage: Union[float, int, list[Union[int, float]]] = 1):
        """_summary_

        Args:
            loan_amount (_type_): _description_
            annual_interest_rate (_type_): _description_
            annual_insurance_rate (_type_): _description_
            monthly_repayment (int, optional): _description_. Defaults to 0.
            insured_number (int, optional): _description_. Defaults to 1.
            insurance_coverage (Union[float, int, list], optional): _description_. Defaults to 1.
        """
        # TODO Docstring
        self.loan_amount = to_decimal(loan_amount)
        self.annual_interest_rate = to_decimal(annual_interest_rate, precision="0.00001")

        self.insured_number = insured_number  # TODO To quantize?
        # Insurance Rate, e.g. x%
        self.annual_insurance_rate = self._format_insurance_related_values(to_decimal(annual_insurance_rate, precision="0.00001"), precision="0.00001")
        # Insurance coverage, e.g. 50% or 100% of the total insurance coverage from 0% to 100%
        self.insurance_coverage = self._format_insurance_related_values(to_decimal(insurance_coverage))

        self.monthly_repayment = to_decimal(monthly_repayment)
        self.loan_amortization_table = None

    def _format_insurance_related_values(self, insurance_value: Union[_Decimal, list[_Decimal]], 
                                         insured_number: Optional[int] = None, precision: str = "0.01") -> list[_Decimal]:
        """Format values related to insurance."""
        if not insured_number:
            insured_number = self.insured_number
        if insured_number == 1 and not isinstance(insurance_value, list):
            return [to_decimal(insurance_value, precision=precision)]
        if isinstance(insurance_value, list) and insured_number == 1:
            return [to_decimal(insurance_value[0], precision=precision)]
        elif insured_number > 1 and not isinstance(insurance_value, list):
            ret_insurance_value = []
            for i in range(self.insured_number):
                ret_insurance_value.append(to_decimal(insurance_value, precision=precision))
            return ret_insurance_value
        elif insured_number > 1 and isinstance(insurance_value, list):
            ret_insurance_value = []
            for _, ins_value in zip(range(insured_number), insurance_value):
                ret_insurance_value.append(to_decimal(ins_value, precision=precision))
            return ret_insurance_value
        else:
            return []

    def validate_refunded_capital(self, monthly_repayment: _Decimal, insurance_N1: _Decimal, remaining_capital: _Decimal, annual_interest_rate: _Decimal,
                                  capital_tolerance: Union[int, float, _Decimal]=0.1):
        """_summary_

        Args:
            monthly_repayment (_type_): _description_
            insurance_N1 (_type_): _description_
            remaining_capital (_type_): _description_
            annual_interest_rate (_type_): _description_
            capital_tolerance (float, optional): _description_. Defaults to 0.1.

        Returns:
            _type_: _description_
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

    def calculated_monthly_insurance(self, remaining_capital: _Decimal,
                                     annual_insurance_rate: Optional[Union[_Decimal, list[_Decimal]]] = None,
                                     insurance_coverage: Optional[Union[_Decimal, list[_Decimal]]] = None,
                                     insured_number: Optional[int] = None):
        """_summary_

        Args:
            remaining_capital (_type_): _description_
            annual_insurance_rate (_type_, optional): _description_. Defaults to None.
            insurance_coverage (_type_, optional): _description_. Defaults to None.
            insured_number (_type_, optional): _description_. Defaults to None.

        Returns:
            _type_: _description_
        """
        # TODO Docstring + translation
        monthly_insurance_cost = 0
        
        if not annual_insurance_rate:
            formatted_annual_insurance_rate = self._format_insurance_related_values(self.annual_insurance_rate, insured_number=insured_number, precision="0.00001")
        else:
            formatted_annual_insurance_rate = self._format_insurance_related_values(annual_insurance_rate, insured_number=insured_number, precision="0.00001")
        if not insurance_coverage:
            formatted_insurance_coverage = self._format_insurance_related_values(self.insurance_coverage, insured_number=insured_number)
        else:
            formatted_insurance_coverage = self._format_insurance_related_values(insurance_coverage, insured_number=insured_number)
        for annual_rate, coverage in zip(formatted_annual_insurance_rate, formatted_insurance_coverage):
            monthly_insurance_cost += remaining_capital * ((annual_rate * coverage) / 12)
        return monthly_insurance_cost

    def calculate_loan_amortization_table(self, duration, initial_loan_amount: _Decimal, annual_interest_rate: _Decimal,
                                          monthly_repayment: _Decimal, capital_tolerance: Union[int, float] = 0.1,
                                          annual_insurance_rate: Optional[Union[_Decimal, list[_Decimal]]] = None,
                                          insured_number: int = 1, insurance_coverage: Optional[Union[_Decimal, list[_Decimal]]] = None):
        """_summary_

        Args:
            duration (_type_): _description_
            initial_loan_amount (_type_): _description_
            annual_interest_rate (_type_): _description_
            monthly_repayment (_type_): _description_
            capital_tolerance (float, optional): _description_. Defaults to 0.1.
            annual_insurance_rate (_type_, optional): _description_. Defaults to None.
            insured_number (int, optional): _description_. Defaults to 1.
            insurance_coverage (_type_, optional): _description_. Defaults to None.

        Returns:
            _type_: _description_
        """
        # TODO Docstring
        loan_amortization_table = {"month": [1], "interest": None, "insurance": None, "refunded_capital": None, "remaining_capital": None, "cumulated_costs": None}

        loan_amortization_table["interest"] = [quantize_amount(initial_loan_amount * annual_interest_rate / 12)]
        loan_amortization_table["insurance"] = [quantize_amount(self.calculated_monthly_insurance(remaining_capital=initial_loan_amount, annual_insurance_rate=annual_insurance_rate,
                                                                                                  insurance_coverage=insurance_coverage, insured_number=insured_number))]
        loan_amortization_table["refunded_capital"] = [quantize_amount(monthly_repayment - loan_amortization_table["interest"][-1] - loan_amortization_table["insurance"][-1])]
        loan_amortization_table["remaining_capital"] = [quantize_amount(initial_loan_amount - loan_amortization_table["refunded_capital"][-1])]
        loan_amortization_table["cumulated_costs"] = [quantize_amount(loan_amortization_table["interest"][-1] + loan_amortization_table["insurance"][-1])]

        for i in range(1, duration):
            loan_amortization_table["month"].append(i + 1)
            loan_amortization_table["insurance"].append(quantize_amount(self.calculated_monthly_insurance(remaining_capital=loan_amortization_table["remaining_capital"][-1],
                                                                                annual_insurance_rate=annual_insurance_rate, insurance_coverage=insurance_coverage, insured_number=insured_number)))
            
            interest, current_refunded_capital, current_remaining_capital = self.validate_refunded_capital(monthly_repayment=monthly_repayment, insurance_N1=loan_amortization_table["insurance"][-1],
                                    remaining_capital=loan_amortization_table["remaining_capital"][-1], annual_interest_rate=annual_interest_rate, capital_tolerance=capital_tolerance)
            loan_amortization_table["interest"].append(quantize_amount(interest))
            loan_amortization_table["refunded_capital"].append(quantize_amount(current_refunded_capital))
            loan_amortization_table["remaining_capital"].append(quantize_amount(current_remaining_capital))
            loan_amortization_table["cumulated_costs"].append(loan_amortization_table["cumulated_costs"][-1] + loan_amortization_table["interest"][-1] + loan_amortization_table["insurance"][-1])
        
        return loan_amortization_table
