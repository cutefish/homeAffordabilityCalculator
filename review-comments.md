# Code Review: Home Affordability Calculator

## Executive Summary

This is a well-structured financial simulation engine for analyzing home affordability decisions. The codebase demonstrates good architecture with clear separation of concerns, proper use of Python dataclasses, and comprehensive financial modeling. However, there are several issues ranging from potential bugs to design improvements that should be addressed.

---

## 1. Critical Issues

### 1.1 Bug: RSU Vesting Income Not Added to Cash (`simulation_engine.py:561`)

```python
# Apply all cash flows
self._cash += gross_income + sale_proceeds
self._cash -= sum(housing_costs.values())
```

**Problem:** When RSUs vest, their value is recorded as `vest_income` and added to `_ytd_income` for tax purposes, but the actual cash proceeds are never added to `_cash`. RSU vesting typically involves selling shares to cover taxes (sell-to-cover), so there should be cash impact.

**Impact:** The simulation may undercount available cash for home purchase if the user expects to use RSU proceeds.

### 1.2 Bug: Arbitrary 30/70 Split for Capital Gains (`simulation_engine.py:517-519`)

```python
if sale_gains >= 0:
    # Determine if gains are short or long term based on what was sold
    # Simplified: add to appropriate bucket
    self._ytd_short_term_gains += sale_gains * 0.3  # Rough estimate
    self._ytd_long_term_gains += sale_gains * 0.7
```

**Problem:** The code uses a hardcoded 30/70 split for short/long-term gains instead of tracking the actual split from `_process_rsu_sales()`. The function already calculates the term for each lot sold.

**Impact:** Inaccurate YTD tracking affects subsequent tax calculations.

### 1.3 Bug: Rent Scenario RSU Holdings Not Updated (`simulation_engine.py:892-958`)

In `_simulate_rent_month()`, the `rsu_holdings` parameter is passed but never mutated to add new vested lots. The rent scenario only calculates vest income but doesn't track the holdings properly for RSU value calculations.

---

## 2. Logic Issues

### 2.1 Debt Balance Never Decreases (`simulation_engine.py`)

The `DebtObligation` class has `remaining_balance` but the simulation never reduces it when payments are made. Over a 10-year simulation, debts that should be paid off continue to have monthly payments.

### 2.2 PMI Rate Hardcoded vs. Configurable (`simulation_engine.py:264,873`)

```python
# In HomeState class
pmi_rate: float = 0.005

# But later:
costs['pmi'] = home.mortgage.remaining_balance * 0.005 / 12  # Hardcoded!
```

The `pmi_rate` field exists but is ignored; the calculation uses a hardcoded 0.005.

### 2.3 Rent Scenario Doesn't Process RSU Sales (`simulation_engine.py:940-941`)

```python
rsu_sale_proceeds=0,
rsu_sale_gains=0,
```

The rent scenario never sells RSUs, which creates an apples-to-oranges comparison. In reality, someone renting might also sell RSUs for other purposes or follow the same selling strategy.

---

## 3. Code Quality Issues

### 3.1 Unused Variable `vested_lots` (`simulation_engine.py:508`)

```python
vest_income, vested_lots = self._process_rsu_vests(current_date)
```

The `vested_lots` return value is never used.

### 3.2 Inconsistent Deduction Logic (`tax_calculator.py:447-448`)

```python
effective_deduction = max(standard, itemized) if not use_standard_deduction else standard
use_std = effective_deduction == standard
```

This logic is confusing. If `use_standard_deduction=True`, it forces standard deduction. If `False`, it picks the larger. The naming is counterintuitive—setting `use_standard_deduction=False` doesn't mean "don't use standard," it means "pick the better option."

### 3.3 Magic Numbers

Several magic numbers throughout the code:
- `simulation_engine.py:792`: `closing_costs = plan.loan_amount * 0.03`
- `simulation_engine.py:647`: `growth = 1.03 ** years_beyond`
- Various tax thresholds should have named constants

---

## 4. Design Recommendations

### 4.1 Missing Type Annotations

Some methods lack return type annotations:
- `_calculate_housing_costs` returns `dict` but should be `dict[str, float]`

### 4.2 Consider Using `Decimal` for Financial Calculations

Using `float` for money calculations can lead to precision issues. For a financial calculator, `decimal.Decimal` would be more appropriate.

### 4.3 No Validation on Inputs

`SimulationInputs` accepts any values without validation:
- Negative salaries
- Down payment percent > 100%
- Mortgage rate > 100%

Consider adding `__post_init__` validation.

### 4.4 State Mutation Makes Testing Difficult

The `FinancialSimulator` mutates internal state during `run()`, meaning you can't re-run a simulation. Consider immutable patterns or explicit reset capability.

---

## 5. Tax Calculation Issues

### 5.1 California SALT Deduction (`tax_calculator.py:474`)

```python
state_tax = self.calculate_california_income_tax(
    total_income=total_income,
    use_standard_deduction=True  # CA has limited itemized benefit
)
```

The comment is misleading. California does allow itemized deductions, just with different rules than federal. This should be configurable.

### 5.2 Missing AMT Calculation

For high earners with RSUs and significant capital gains, Alternative Minimum Tax (AMT) can be significant but isn't modeled.

### 5.3 Tax Year Hardcoded to 2024

All tax brackets and constants are for 2024. For a 10-year simulation, taxes will change. Consider adding inflation adjustments or year-specific brackets.

---

## 6. Missing Features

### 6.1 No Support for:
- 401(k) contributions and employer match
- IRA contributions
- Health insurance premiums
- Child tax credits
- Property tax Prop 13 assessments (important for California)
- Mortgage interest deduction phase-outs at high income
- Capital loss carryforward

### 6.2 No Input Validation or Error Handling

The code assumes all inputs are valid and complete. No try/except blocks for edge cases.

---

## 7. Documentation

### 7.1 Good Practices
- Comprehensive docstrings on classes and key methods
- Clear module-level documentation
- Well-organized section headers

### 7.2 Areas for Improvement
- No inline comments for complex tax calculations
- No documentation on the algorithm for `_process_rsu_sales`

---

## 8. Testing

**No test suite exists.** For financial calculations, this is a significant gap. Recommended test coverage:

1. Tax bracket edge cases
2. RSU selling strategy behavior
3. Mortgage amortization accuracy
4. PMI removal timing
5. Year-over-year consistency

---

## 9. Minor Issues

| File | Line | Issue |
|------|------|-------|
| `tax_calculator.py` | 527 | `effective_federal_after_salt` calculation seems incorrect—SALT cap is $10k, not based on state rate |
| `simulation_engine.py` | 857 | Rent scenario returns `comparable_rent` even after home purchase—should be 0 |
| `run_simulation.py` | 251 | Prints 2026 detail but home is purchased in June 2025 |

---

## 10. Security

No security concerns for this type of application. It's a local calculation tool with no network access, file writes (except CSV export), or user input handling beyond the example script.

---

## Summary Table

| Category | Rating | Notes |
|----------|--------|-------|
| Architecture | ⭐⭐⭐⭐ | Clean separation, good use of dataclasses |
| Correctness | ⭐⭐⭐ | Several bugs in RSU/tax tracking |
| Code Style | ⭐⭐⭐⭐ | Consistent, readable, follows Python conventions |
| Documentation | ⭐⭐⭐⭐ | Good docstrings, clear structure |
| Testing | ⭐ | No tests present |
| Maintainability | ⭐⭐⭐ | Some magic numbers, state mutation concerns |

---

## Priority Fixes

1. **High**: Fix RSU vesting cash flow bug
2. **High**: Track actual short/long-term gains instead of arbitrary split
3. **Medium**: Reduce debt balances over time
4. **Medium**: Use configurable PMI rate
5. **Medium**: Add input validation
6. **Low**: Add test suite
7. **Low**: Consider year-specific tax brackets
