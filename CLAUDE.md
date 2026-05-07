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

The repo is the `budget_simulator` Python package itself (`__init__.py` re-exports `LoanCalculator`). All source files sit at the root level; there is no `src/` layout. The package is imported as `from budget_simulator.loan_calculator import LoanCalculator`.

### `_utils.py`

Two helpers used throughout the package:
- `to_decimal(value, precision)` — converts `int`/`float` to `Decimal` at a given precision (default `"0.01"`). Always converts through `str()` to avoid float representation drift.
- `quantize_amount(value)` — snaps any `Decimal` to 2 d.p. (cents). Raises `TypeError` if the input is not already a `Decimal`.

### `loan_calculator.py` — `LoanCalculator`

The main public API.

**Constructor** takes `loan_amount`, `annual_interest_rate`, `annual_insurance_rate`, optional `monthly_repayment`, `insured_number`, and `insurance_coverage`. Insurance parameters are normalised internally to `list[Decimal]` via `_format_insurance_related_values`, supporting one or two insured persons with independent rates and coverage ratios. The instance attribute `loan_amortization_table` is initialised to `None` and is **not** updated by any method — the methods return the table directly.

**Private helpers:**

- **`_format_insurance_related_values(value, insured_number, precision)`** — normalises a scalar or list insurance parameter into `list[Decimal]` of length `insured_number`. Called at construction for both `annual_insurance_rate` and `insurance_coverage`.

- **`_compute_monthly_insurance(remaining_capital)`** — `Σ remaining_capital × (annual_rate × coverage / 12)` across all insured persons. Returns an unquantized `Decimal`; callers must apply `quantize_amount`.

- **`_compute_payment_breakdown(monthly_repayment, monthly_insurance, remaining_capital, capital_tolerance)`** — core per-month decomposition: computes interest, repaid capital, and new remaining balance. Applies a tolerance cap: if the residual difference is less than `monthly_repayment × capital_tolerance`, the entire remaining balance is treated as repaid (avoids a rounding-driven micro-payment on the final month). Returns a 3-tuple `(interest, repaid_capital, remaining_capital)`.

- **`_compute_analytical_monthly_repayment(principal, duration)`** — uses the standard fixed-rate amortization formula (briefly via `float` — the only acceptable place) to compute the exact monthly repayment that amortizes `principal` over `duration` months. Uses an effective monthly rate that folds in insurance alongside interest.

**Public methods:**

- **`calculate_loan_amortization_table(duration, monthly_repayment, early_repayment, early_repayment_month, capital_tolerance, initial_capital)`** — builds a month-by-month dict with keys `month`, `interest`, `insurance`, `refunded_capital`, `remaining_capital`, `cumulated_costs`. Stops early when remaining capital reaches zero. The optional `initial_capital` parameter overrides `self.loan_amount` as the starting balance (used internally by Strategy B Phase 2). An optional one-time `early_repayment` lump sum is subtracted from the outstanding balance at `early_repayment_month` before that month's computation.

- **`calculate_monthly_repayment_and_loan_amortization_table(duration, monthly_repayment, early_repayment, early_repayment_month, capital_tolerance)`** — two distinct execution paths:
  - **No early repayment (iterative solver):** repeatedly adjusts `monthly_repayment` via a `capital_ratio` heuristic until the table ends with zero remaining capital exactly at `duration`. Falls back to a fixed `-0.5` capital_ratio when the solver stalls. Returns `(table, final_monthly_repayment)`.
  - **With early repayment (Strategy B):** two-phase approach — Phase 1 runs the original repayment from month 1 to `early_repayment_month`; Phase 2 calls `_compute_analytical_monthly_repayment` on the reduced principal and runs for `duration - early_repayment_month` months. The two tables are merged into one spanning exactly `duration` rows, with `cumulated_costs` offset-adjusted at the boundary. Returns `(merged_table, phase2_repayment)`.

### `budget_calculator.py`

Currently empty; intended for budget-level calculations.

## Precision conventions

All monetary values use `Decimal` quantized to `"0.01"` (cents). Rates use `"0.00001"`. The only permitted use of `float` arithmetic is inside `_compute_analytical_monthly_repayment` for the exponentiation formula. Never use `float` elsewhere for financial values — always go through `to_decimal` / `quantize_amount`.

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
