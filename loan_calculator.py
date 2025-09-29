import numpy as np
import pandas as pd
from decimal import Decimal as _Decimal

from ._utils import quantize_amount


class LoanCalculator():

    def __init__(self, loan_amount, annual_interest_rate, annual_insurance_rate,
                 monthly_repayment=0, insured_number=1, insurance_coverage=1):
        self.loan_amount = loan_amount
        self.annual_interest_rate = annual_interest_rate

        self.annual_insurance_rate = self._format_insurance_related_values(annual_insurance_rate)
        self.insured_number = self._format_insurance_related_values(insured_number)
        self.insurance_coverage = self._format_insurance_related_values(insurance_coverage)

        self.monthly_repayment = monthly_repayment
        self.loan_amortization_table = None

    def _format_insurance_related_values(self, insurance_value):
        """Format values related to insurance."""
        return insurance_value if isinstance(insurance_value, list) else [insurance_value]

    def validate_refunded_capital(self, monthly_repayment, insurance_N1, remaining_capital, annual_interest_rate, tolerance=0.1):
        """"""
        # TODO Docstring + translation
        tolerance = _Decimal(tolerance).quantize(_Decimal("0.00001"))

        interest = remaining_capital * annual_interest_rate / 12
        current_refunded_capital = monthly_repayment - interest - insurance_N1
        refunded_capital_difference = remaining_capital - current_refunded_capital
        if refunded_capital_difference < monthly_repayment * tolerance:
            current_refunded_capital = remaining_capital
            current_remaining_capital = 0
        else:
            current_remaining_capital = remaining_capital - current_refunded_capital
        return interest, current_refunded_capital, _Decimal(current_remaining_capital)

    def calculated_monthly_insurance(self, assurance_solo, montant_pret_initial, taux_assurance_annuel):
        """"""
        # TODO Docstring + translation
        if assurance_solo:
            return montant_pret_initial * taux_assurance_annuel / 18
        else:
            return montant_pret_initial * taux_assurance_annuel / 12

    def calculate_loan_amortization_table(self, duration, initial_loan_amount, annual_interest_rate, annual_insurance_rate,
                                          monthly_repayment, insured_number=1, tolerance=0.1):
        loan_amortization_table = {"month": [1], "interest": None, "insurance": None, "refunded_capital": None, "remaining_capital": None, "cumulated_costs": None}

        loan_amortization_table["interest"] = [quantize_amount(initial_loan_amount * annual_interest_rate / 12)]
        loan_amortization_table["insurance"] = [quantize_amount(self.calculated_monthly_insurance(assurance_solo=assurance_solo, montant_pret_initial=montant_pret_initial,
                                                                                taux_assurance_annuel=taux_assurance_annuel))]
        loan_amortization_table["refunded_capital"] = [quantize_amount(monthly_repayment - loan_amortization_table["interest"][-1] - loan_amortization_table["insurance"][-1])]
        loan_amortization_table["remaining_capital"] = [quantize_amount(initial_loan_amount - loan_amortization_table["refunded_capital"][-1])]
        loan_amortization_table["cumulated_costs"] = [quantize_amount(loan_amortization_table["interest"][-1] + loan_amortization_table["insurance"][-1])]

        for i in range(1, duration):
            loan_amortization_table["month"].append(i + 1)
            loan_amortization_table["insurance"].append(quantize_amount(self.calculated_monthly_insurance(assurance_solo=assurance_solo, montant_pret_initial=loan_amortization_table["capital_restant"][-1],
                                                                                taux_assurance_annuel=taux_assurance_annuel)))
            
            interest, current_refunded_capital, current_remaining_capital = self.validate_refunded_capital(monthly_repayment=monthly_repayment, insurance_N1=loan_amortization_table["insurance"][-1],
                                    remaining_capital=loan_amortization_table["remaining_capital"][-1], annual_interest_rate=annual_interest_rate)  # , tolerance=tolerance)
            loan_amortization_table["interest"].append(quantize_amount(interest))
            loan_amortization_table["refunded_capital"].append(quantize_amount(current_refunded_capital))
            loan_amortization_table["remaining_capital"].append(quantize_amount(current_remaining_capital))
            loan_amortization_table["cumulated_costs"].append(loan_amortization_table["cumulated_costs"][-1] + loan_amortization_table["interest"][-1] + loan_amortization_table["insurance"][-1])
        
        return loan_amortization_table