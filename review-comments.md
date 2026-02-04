# Code Review: Home Affordability Calculator

## Branch: `claude/house-affordability-calculator-QLGgA`

**Review Date:** 2026-02-04
**Review Round:** 3

---

## Executive Summary

This round of review confirms that all critical and high-priority issues from the previous review have been properly addressed. The codebase is now in good shape with proper RSU sell-to-cover mechanics, extracted constants, and comprehensive test coverage.

**Changes Since Last Review:**
- `simulation_engine.py`: +62/-40 lines (sell-to-cover implementation, constants)
- `test_financial_concepts.py`: +14/-13 lines (updated tests for sell-to-cover)
- `review-response.md`: +334 lines (detailed response to review)

---

## 1. Previously Identified Issues - Status

### 1.1 ✅ FIXED: RSU Vest Withholding / Share Count Mismatch

**Previous Issue:** RSU withholding deducted cash but full shares remained in holdings (double-taxation).

**Fix Implemented:** Proper sell-to-cover behavior now implemented:
```python
# RSU vest withholding rate (sell-to-cover)
RSU_VEST_WITHHOLDING_RATE = 0.37

# In _process_rsu_vests():
shares_after_withholding = int(vest.shares * (1 - RSU_VEST_WITHHOLDING_RATE))
```

The cash deduction was removed since shares are now reduced instead. This correctly models how RSU vesting works at most tech companies.

**Verification:** Test `test_rsu_vest_adds_income_and_holdings` updated to verify:
- Full vest value recorded as income ($15,000 for 100 shares @ $150)
- Only 63 shares kept after sell-to-cover (100 × 0.63 = 63)
- Holdings value = 63 × $150 = $9,450

### 1.2 ✅ FIXED: Rent Scenario YTD Income Double-Counting

**Previous Issue:** `vest_income` accumulated in loop and was added cumulatively to `ytd_income`.

**Fix Implemented:**
```python
# Before (bug):
vest_income += vest.shares * stock_price
ytd_income += vest_income  # Cumulative - BUG

# After (fixed):
this_vest_value = vest.shares * stock_price
vest_income += this_vest_value
ytd_income += this_vest_value  # Individual value
```

### 1.3 ✅ FIXED: Magic Numbers Extracted to Constants

**Previous Issue:** Hardcoded 0.37 withholding rate and 0.03 closing cost rate.

**Fix Implemented:**
```python
# =============================================================================
# CONSTANTS
# =============================================================================

RSU_VEST_WITHHOLDING_RATE = 0.37
CLOSING_COST_RATE = 0.03
```

Both constants include documentation explaining their values.

### 1.4 ✅ FIXED: Added `total_housing_payment` Property

**Previous Issue:** Only `total_housing_cost` existed (excludes principal), which could confuse users.

**Fix Implemented:**
```python
@property
def total_housing_payment(self) -> float:
    """Total housing payment including principal (what you actually pay each month)."""
    if self.rent > 0:
        return self.rent
    return (
        self.mortgage_principal + self.mortgage_interest +
        self.property_tax + self.homeowners_insurance +
        self.pmi + self.hoa + self.maintenance
    )
```

Users can now use:
- `total_housing_cost` - for true cost analysis (excludes equity-building principal)
- `total_housing_payment` - for cash flow analysis (actual monthly outlay)

---

## 2. New Review Findings

### 2.1 Minor: Sell-to-Cover Uses Integer Truncation

```python
shares_after_withholding = int(vest.shares * (1 - RSU_VEST_WITHHOLDING_RATE))
```

Using `int()` truncates rather than rounds. For 100 shares:
- `int(100 * 0.63)` = 63 shares ✓ (correct)
- `int(10 * 0.63)` = 6 shares (6.3 truncated)

**Impact:** Minor. Most RSU vests are in larger quantities. Real brokers may round differently but the simulation is close enough.

**Recommendation:** No action needed; current behavior is acceptable.

### 2.2 Minor: Rent Scenario Also Uses Sell-to-Cover Now

The rent scenario now properly mirrors the buy scenario with sell-to-cover:
```python
shares_after_withholding = int(vest.shares * (1 - RSU_VEST_WITHHOLDING_RATE))
```

This is correct - both scenarios should use the same vesting mechanics.

### 2.3 Observation: Comprehensive Review Response

The `review-response.md` file provides excellent documentation of:
- What was fixed and how
- What was acknowledged but deferred
- Rationale for design decisions

This is good practice for tracking code review outcomes.

---

## 3. Remaining Lower-Priority Items (Acknowledged)

These items were acknowledged in `review-response.md` as future improvements:

| Item | Status | Notes |
|------|--------|-------|
| `Decimal` for money | Deferred | Float precision adequate for simulation |
| State mutation | Deferred | Create new simulator instance for each run |
| Tax year brackets | Deferred | Uses 2024 brackets; could add inflation adjustment |
| AMT calculation | Deferred | Complex; affects small subset of users |
| 401(k)/IRA support | Deferred | Future feature |

---

## 4. Test Coverage Review

The test file was updated to reflect sell-to-cover behavior:

```python
# RSU holdings reflect sell-to-cover: only ~63% of shares kept
shares_after_withholding = int(100 * (1 - 0.37))  # 63 shares
expected_holdings = shares_after_withholding * 150.0  # $9,450
assert mar.rsu_holdings_value == expected_holdings
```

**Test Output Improved:**
```
RSU vesting with sell-to-cover (100 shares @ $150):
  Vest income (full, for taxes): $15,000
  Shares withheld for taxes: 37 (~37%)
  Shares kept: 63
  RSU holdings value: $9,450
```

This educational output helps users understand the sell-to-cover mechanism.

---

## 5. Code Quality Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| Bug fixes | ✅ Complete | All critical/high issues resolved |
| Constants | ✅ Added | Magic numbers extracted |
| Documentation | ✅ Good | Clear comments on constants and methods |
| Tests | ✅ Updated | Reflect new sell-to-cover behavior |
| Code style | ✅ Consistent | Follows existing patterns |

---

## 6. Summary Table

| Category | Previous | Current | Change |
|----------|----------|---------|--------|
| Architecture | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | — |
| Correctness | ⭐⭐⭐⭐ | ⭐⭐⭐⭐½ | +½ (sell-to-cover fixed) |
| Code Style | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | — |
| Documentation | ⭐⭐⭐⭐ | ⭐⭐⭐⭐½ | +½ (review-response.md) |
| Testing | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | — |
| Maintainability | ⭐⭐⭐½ | ⭐⭐⭐⭐ | +½ (constants extracted) |

---

## 7. Conclusion

**All issues from the previous review have been properly addressed:**

1. ✅ RSU sell-to-cover now correctly reduces share count instead of deducting cash
2. ✅ YTD income double-counting bug fixed in rent scenario
3. ✅ Magic numbers extracted to named constants with documentation
4. ✅ Added `total_housing_payment` property for cash flow clarity
5. ✅ Tests updated to verify sell-to-cover behavior

The implementation is correct and follows real-world RSU vesting mechanics. The code is well-documented and maintainable.

**Recommendation:** ✅ **APPROVE** - Ready for merge.

---

## Appendix: Files Changed

```
simulation_engine.py       | 102 +++++++++-----
test_financial_concepts.py |  27 ++--
review-response.md         | 334 +++++++++++++++++++++++++++++++++++++++++++++
```
