# Code Review: Home Affordability Calculator

## Branch: `claude/house-affordability-calculator-QLGgA`

**Review Date:** 2026-02-04

---

## Executive Summary

This branch contains significant improvements to the home affordability calculator, addressing many issues from the previous review. The changes include bug fixes for RSU handling, debt amortization, tax calculations, and the addition of a comprehensive educational test suite. The code quality has improved substantially.

**Key Changes Reviewed:**
- `simulation_engine.py`: +195 lines (major fixes and improvements)
- `tax_calculator.py`: -2 lines (removed incorrect calculation)
- `test_financial_concepts.py`: +749 lines (new educational test suite)

---

## 1. Issues Fixed (from Previous Review)

### 1.1 ✅ Fixed: Arbitrary 30/70 Split for Capital Gains

**Before:**
```python
self._ytd_short_term_gains += sale_gains * 0.3  # Rough estimate
self._ytd_long_term_gains += sale_gains * 0.7
```

**After:** The problematic `_ytd_short_term_gains` and `_ytd_long_term_gains` variables have been removed entirely. Tax calculations now use the actual gain term from each sale.

### 1.2 ✅ Fixed: Debt Balance Never Decreases

**Before:** Debts were charged monthly but balance never reduced.

**After:** Proper debt amortization implemented:
```python
for debt in self._debts:
    if debt.remaining_balance > 0:
        monthly_interest = debt.remaining_balance * (debt.interest_rate / 12)
        principal_payment = debt.monthly_payment - monthly_interest
        if principal_payment > debt.remaining_balance:
            principal_payment = debt.remaining_balance
        debt.remaining_balance -= principal_payment
```

### 1.3 ✅ Fixed: PMI Rate Hardcoded

**Before:** Used hardcoded `0.005` instead of `home.pmi_rate`.

**After:** Uses configurable rate:
```python
costs['pmi'] = home.mortgage.remaining_balance * home.pmi_rate / 12
```

### 1.4 ✅ Fixed: Rent Scenario Doesn't Process RSU Sales

**Before:** Rent scenario hardcoded `rsu_sale_proceeds=0`.

**After:** Rent scenario now fully processes RSU sales with the same strategies (except `SELL_AT_PURCHASE` which doesn't apply to renters).

### 1.5 ✅ Fixed: Rent Scenario RSU Holdings Not Updated

**Before:** Vested lots weren't added to rent scenario holdings.

**After:** New vested lots are properly added:
```python
new_lot = RSULot(
    lot_id=vest.vest_id,
    shares=vest.shares,
    cost_basis_per_share=stock_price,
    vest_date=vest.vest_date
)
rsu_holdings.append(new_lot)
```

### 1.6 ✅ Fixed: Unused Variable `vested_lots`

**Before:** `_process_rsu_vests` returned tuple with unused second element.

**After:** Returns only `vest_income`:
```python
def _process_rsu_vests(self, current_date: date) -> float:
    """Process RSU vests for this month. Returns vest income."""
```

### 1.7 ✅ Fixed: No Input Validation

**After:** Added `__post_init__` validation for `HousePurchasePlan` and `SimulationInputs`:
```python
def __post_init__(self):
    if self.home_price <= 0:
        raise ValueError("home_price must be positive")
    if not 0 <= self.down_payment_percent <= 1:
        raise ValueError("down_payment_percent must be between 0 and 1")
    # ... more validation
```

### 1.8 ✅ Fixed: Incorrect `effective_federal_after_salt` Calculation

**Before:** `tax_calculator.py` had incorrect SALT-related calculation.

**After:** Removed the problematic field entirely.

### 1.9 ✅ Fixed: No Test Suite

**After:** Added comprehensive `test_financial_concepts.py` with 749 lines of educational tests.

---

## 2. New Issues Identified

### 2.1 Bug: RSU Vest Withholding Applied but Shares Still in Holdings

In `simulation_engine.py`, when RSUs vest:
```python
# RSU vest withholding (typically ~37% in CA)
rsu_vest_withholding = vest_income * 0.37 if vest_income > 0 else 0
self._cash -= rsu_vest_withholding
```

**Problem:** The withholding is deducted from cash, but the full number of shares remains in holdings. In reality, "sell-to-cover" would reduce the share count. This creates a mismatch where the user "pays" the tax twice—once via withholding, and again when selling RSUs that should have been reduced.

**Suggested Fix:** Either:
1. Reduce shares by ~37% at vesting (simulating sell-to-cover), OR
2. Don't deduct withholding from cash but track it as future tax liability

### 2.2 Inconsistency: Total Housing Cost Excludes Principal

```python
@property
def total_housing_cost(self) -> float:
    """True housing cost (excludes principal which builds equity)."""
    return (
        self.mortgage_interest +  # Principal excluded
        self.property_tax + ...
    )
```

While conceptually correct (principal builds equity), this may confuse users comparing to their actual mortgage payment. Consider:
- Adding a separate `total_housing_payment` property that includes principal
- Clarifying in output that this is "cost" not "payment"

### 2.3 Magic Number: RSU Withholding Rate

```python
rsu_vest_withholding = vest_income * 0.37 if vest_income > 0 else 0
```

The 37% is a reasonable California estimate but should be:
1. A named constant (e.g., `RSU_VEST_WITHHOLDING_RATE = 0.37`)
2. Potentially configurable per state

### 2.4 Closing Costs Calculation Changed but May Be Less Accurate

**Before:** `closing_costs = plan.loan_amount * 0.03`
**After:** `closing_costs = plan.home_price * 0.03`

Both are approximations, but closing costs are typically a percentage of the loan amount (for lender fees) plus fixed costs. Using home price makes larger down payments appear to have higher closing costs, which isn't quite right.

### 2.5 Rent Scenario YTD Income Double-Counting

In `_simulate_rent_month`:
```python
ytd_income += gross_income
# ...
for vest in self.inputs.future_rsu_vests:
    if (vest.vest_date.year == year and vest.vest_date.month == month):
        vest_income += vest.shares * stock_price
        ytd_income += vest_income  # Bug: This adds cumulative vest_income
```

**Problem:** If there are multiple vests in the same month, `vest_income` accumulates, and each iteration adds the cumulative amount to `ytd_income`. Should be `ytd_income += vest.shares * stock_price` instead.

---

## 3. Test Suite Review (`test_financial_concepts.py`)

### 3.1 Strengths

1. **Educational Value**: Excellent documentation explaining financial concepts inline
2. **Coverage**: Tests mortgage calculations, tax brackets, capital gains, RSU mechanics, and input validation
3. **Practical Examples**: Uses realistic numbers that help users understand the concepts

### 3.2 Areas for Improvement

| Issue | Location | Description |
|-------|----------|-------------|
| No negative test for RSU sales | `TestRSUMechanics` | Should test selling more shares than owned |
| Missing PMI removal test | - | No test verifying PMI is removed at 80% LTV |
| Missing breakeven test | - | No test for buy-vs-rent breakeven calculation |
| Hardcoded dates | Throughout | Tests use 2025 dates that will become stale |

### 3.3 Test Code Quality Issue

```python
def test_home_purchase_affects_net_worth(self):
    # ...
    assert mar.cash_balance < feb.cash_balance - 150_000, \
        f"Cash should drop after down payment. Feb: ${feb.cash_balance:,.0f}, Mar: ${mar.cash_balance:,.0f}"
```

The assertion uses a magic number `150_000`. Should calculate expected drop based on down payment + closing costs.

---

## 4. Code Quality Assessment

### 4.1 Improvements

| Aspect | Before | After |
|--------|--------|-------|
| Input validation | None | Comprehensive `__post_init__` |
| Debt tracking | Static | Proper amortization |
| Rent scenario | Incomplete | Full parity with buy scenario |
| Test coverage | None | Educational test suite |
| PMI calculation | Hardcoded | Configurable |

### 4.2 Remaining Concerns

1. **Float precision**: Still using `float` for money (should consider `Decimal`)
2. **State mutation**: Simulator still can't be re-run
3. **Tax year hardcoding**: Still uses 2024 brackets for multi-year simulations

---

## 5. Summary Table

| Category | Previous | Current | Notes |
|----------|----------|---------|-------|
| Architecture | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Clean design maintained |
| Correctness | ⭐⭐⭐ | ⭐⭐⭐⭐ | Major bugs fixed |
| Code Style | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Consistent |
| Documentation | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Good docstrings |
| Testing | ⭐ | ⭐⭐⭐⭐ | Comprehensive test suite added |
| Maintainability | ⭐⭐⭐ | ⭐⭐⭐½ | Validation added, some magic numbers remain |

---

## 6. Recommendations

### High Priority
1. Fix RSU vest withholding / share count mismatch (Section 2.1)
2. Fix rent scenario YTD income double-counting (Section 2.5)

### Medium Priority
3. Extract magic numbers to named constants (37% withholding, 3% closing costs)
4. Add `total_housing_payment` property for clarity
5. Add PMI removal and breakeven tests

### Low Priority
6. Consider `Decimal` for financial precision
7. Add year-specific tax brackets or inflation adjustment
8. Make test dates relative to avoid staleness

---

## 7. Conclusion

This branch represents a significant improvement over the previous state. The critical bugs around RSU tracking, debt amortization, and rent scenario comparisons have been fixed. The addition of input validation and a comprehensive test suite substantially improves reliability and maintainability.

**Recommendation:** Approve with minor fixes for the RSU withholding mismatch and YTD income double-counting issues.
