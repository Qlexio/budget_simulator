# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python project for French mortgage/home-loan analysis: computing amortization tables, modeling early repayments (remboursement anticipé), and comparing repayment strategies.

## Environment & Commands

Python 3.10.18. The virtual environment is `uv`-managed and lives at `.venv/` inside the repo root. There is **no `pip` binary** — use `uv pip` for all package management.

```bash
# Activate the virtual environment
source .venv/bin/activate

# Launch JupyterLab
jupyter lab

# Add a new package
uv pip install <package>
```

### Testing

A custom `pytest-test-writer` agent lives at `.claude/agents/pytest-test-writer.md`. **Always invoke it after creating or modifying any code.** It is the only agent permitted to create or edit files under `tests/`. It handles environment setup, test layout, and coverage reporting automatically.

Dev dependencies (`pytest`, `pytest-mock`, `pytest-cov`) are declared in `pyproject.toml` under `[dependency-groups] dev`. Install them with:

```bash
uv sync --group dev
# or, as a fallback:
uv pip install pytest pytest-mock pytest-cov --python .venv/bin/python
```

Tests live in `tests/` (mirroring the package structure). Run them:

```bash
# Full suite
.venv/bin/pytest tests/ -vvv

# Single file
.venv/bin/pytest tests/test_loan_calculator.py -vvv

# With coverage
.venv/bin/pytest tests/ --cov=. --cov-report=term-missing
```

Production dependencies (`numpy`, `pandas`) and dev dependencies (`pytest`, `pytest-mock`, `pytest-cov`) are declared in `pyproject.toml`. `jupyter`/`jupyterlab` is installed in the venv but not declared. `decimal` is stdlib.

## Architecture

The repo is the `budget_simulator` Python package itself. All source files sit at the root level; there is no `src/` layout.

### `_utils.py`

Two helpers used throughout the package:
- `to_decimal(value, precision)` — converts `int`/`float` to `Decimal` at a given precision (default `"0.01"`).
- `quantize_amount(value)` — snaps any `Decimal` to 2 d.p. (cents).

### `loan_calculator.py` — `LoanCalculator`

The main public API.

- **Constructor** takes `loan_amount`, `annual_interest_rate`, `annual_insurance_rate`, optional `monthly_repayment`, `insured_number`, and `insurance_coverage`. Insurance parameters are normalised internally to `list[Decimal]` via `_format_insurance_related_values`, supporting one or two insured persons with independent rates and coverage ratios.
- **`calculate_loan_amortization_table(duration, ...)`** — core loop: builds a month-by-month dict of `{month, interest, insurance, refunded_capital, remaining_capital, cumulated_costs}`. Stops early when the loan is fully repaid. Handles a one-time early repayment at a specified month.
- **`calculate_monthly_repayment_and_loan_amortization_table(duration, ..., monthly_repayment)`** — iterative solver: repeatedly adjusts the monthly repayment (via a `capital_ratio` heuristic) until the table ends exactly at `duration` with zero remaining capital. Falls back to a random negative `capital_ratio` when the solver stalls. Still has `print` debug statements.
- **`calculated_monthly_insurance(remaining_capital)`** — `Σ remaining_capital × (annual_rate × coverage / 12)` across all insured persons.
- **`validate_refunded_capital(...)`** — caps the final month's repaid capital at the actual remaining balance.

### `budget_calculator.py`

Currently empty; intended for budget-level calculations.

## Precision conventions

All monetary values use `Decimal` quantized to `"0.01"` (cents). Rates use `"0.00001"`. Never use `float` arithmetic for financial values — always go through `to_decimal` / `quantize_amount`.

## Domain vocabulary (French ↔ English)

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
