# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python project for French mortgage/home-loan analysis: computing amortization tables, modeling early repayments (remboursement anticipé), and comparing repayment strategies.

## Environment & Commands

```bash
# Activate the virtual environment
source banque_venv/bin/activate

# Launch JupyterLab
jupyter lab

# Run a notebook non-interactively
jupyter nbconvert --to notebook --execute <notebook>.ipynb
```

Dependencies: `numpy`, `pandas`, `decimal` (stdlib), `jupyter`/`jupyterlab`. No separate install step — all packages are already present in `banque_venv/`.

## Architecture

### `budget_simulator/` package

- **`_utils.py`** — two helpers used everywhere:
  - `to_decimal(value, precision)` — converts `int`/`float` to `Decimal` at a given precision (default `"0.01"`).
  - `quantize_amount(value)` — snaps any `Decimal` to 2 d.p. (cents).

- **`loan_calculator.py`** — `LoanCalculator` class, the main public API:
  - Constructor takes `loan_amount`, `annual_interest_rate`, `annual_insurance_rate`, optional `monthly_repayment`, `insured_number`, and `insurance_coverage`. Insurance parameters are normalised internally to `list[Decimal]` via `_format_insurance_related_values`, supporting one or two insured persons with independent rates and coverage ratios.
  - `calculate_loan_amortization_table(duration, ...)` — core loop: builds a month-by-month dict of `{month, interest, insurance, refunded_capital, remaining_capital, cumulated_costs}`. Stops early if the loan is fully repaid. Handles a one-time early repayment at a specified month.
  - `calculate_monthly_repayment_and_loan_amortization_table(duration, ..., monthly_repayment)` — iterative solver: repeatedly adjusts the monthly repayment upward (using a `capital_ratio` heuristic) until the table ends exactly at `duration` months with zero remaining capital. Falls back to a random negative `capital_ratio` when the solver stalls. Still has `print` debug statements and rough edges.
  - `calculated_monthly_insurance(remaining_capital)` — computes the combined monthly insurance cost across all insured persons: `Σ remaining_capital × (annual_rate × coverage / 12)`.
  - `validate_refunded_capital(...)` — caps the final month's repaid capital at the actual remaining balance.

- **`budget_calculator.py`** — currently empty, intended for budget-level calculations.

### Notebooks

- **`simulation.ipynb`** — original French-language prototype. Contains standalone functions (`calcul_tableau_amortissement`, `calcul_tableau_amortissement_remb_anticipe_*`) that mirror the class logic. Useful as a reference for the domain model and for one-off experiments. Has a known bug: a `KeyError: 'interests'` (should be `'interets'`).
- **`test.ipynb`** — exercises the `LoanCalculator` class directly. Use this to verify changes to the package.

### Precision conventions

All monetary values use `Decimal` quantized to `"0.01"` (cents). Rates use `"0.00001"`. Never use `float` arithmetic for financial values; always go through `to_decimal` / `quantize_amount`.

### Domain vocabulary (French ↔ English)

| French | English |
|---|---|
| mensualité | monthly repayment |
| taux d'intérêt | interest rate |
| taux d'assurance | insurance rate |
| capital restant dû | remaining capital |
| capital remboursé | refunded / repaid capital |
| remboursement anticipé | early repayment |
| tableau d'amortissement | amortization table |
| coût total cumulé | cumulated total cost |