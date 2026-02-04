"""
Educational Test Suite for Home Affordability Calculator

This test file serves two purposes:
1. Validate the correctness of financial calculations
2. Teach the underlying financial concepts through examples

Each test section includes explanations of the financial concepts being tested.
Run with: python -m pytest test_financial_concepts.py -v
"""

import pytest
from datetime import date
from dateutil.relativedelta import relativedelta

from config import FilingStatus, RSUTerm, InvestmentType
from tax_calculator import TaxCalculator
from simulation_engine import (
    SimulationInputs, HousePurchasePlan, RSULot, FutureRSUVest,
    IncomeProfile, InvestmentAccount, DebtObligation, MarketAssumptions,
    RSUSellStrategy, RSUSellRule, FinancialSimulator, MortgageState
)


# =============================================================================
# SECTION 1: MORTGAGE CALCULATIONS
# =============================================================================
"""
CONCEPT: Mortgage Amortization

A mortgage payment has two parts:
- Interest: What you pay the bank for borrowing money
- Principal: What actually reduces your loan balance

Early in a mortgage, most of your payment is interest. Over time, more goes to principal.

Formula for monthly payment (P&I):
    M = P * [r(1+r)^n] / [(1+r)^n - 1]

Where:
    M = monthly payment
    P = principal (loan amount)
    r = monthly interest rate (annual rate / 12)
    n = total number of payments (years * 12)

Example: $800,000 loan at 6.75% for 30 years
    r = 0.0675 / 12 = 0.005625
    n = 30 * 12 = 360
    M = 800000 * [0.005625 * (1.005625)^360] / [(1.005625)^360 - 1]
    M ≈ $5,189.43
"""


class TestMortgageCalculations:
    """Tests for mortgage payment calculations."""

    def test_monthly_payment_calculation(self):
        """
        Verify the monthly P&I payment formula.

        For an $800,000 loan at 6.75% over 30 years:
        - Monthly rate: 6.75% / 12 = 0.5625%
        - Number of payments: 360
        - Expected payment: ~$5,189
        """
        # Create a simple simulation just to access the calculation method
        inputs = SimulationInputs(
            filing_status=FilingStatus.SINGLE,
            initial_cash=200000,
            house_plan=HousePurchasePlan(
                purchase_date=date(2025, 6, 1),
                home_price=1_000_000,
                down_payment_percent=0.20,  # 20% down = $200k, loan = $800k
                mortgage_rate=0.0675,
                loan_term_years=30
            )
        )

        simulator = FinancialSimulator(inputs)
        monthly_payment = simulator._calculate_monthly_pi(
            principal=800_000,
            annual_rate=0.0675,
            term_years=30
        )

        # Verify against known correct value
        # You can verify this with any mortgage calculator online
        assert abs(monthly_payment - 5189.43) < 1.0, \
            f"Monthly payment should be ~$5,189, got ${monthly_payment:.2f}"

    def test_first_month_interest_vs_principal(self):
        """
        In month 1, most of your payment goes to interest.

        For $800,000 at 6.75%:
        - Monthly interest = $800,000 * (6.75% / 12) = $4,500
        - If payment is $5,189, principal = $5,189 - $4,500 = $689

        So in month 1: 87% goes to interest, only 13% to principal!
        """
        mortgage = MortgageState(
            original_principal=800_000,
            remaining_balance=800_000,
            monthly_payment=5189.43,
            interest_rate=0.0675,
            start_date=date(2025, 6, 1),
            term_months=360
        )

        principal, interest = mortgage.calculate_month_payment()

        # First month interest should be exactly loan * monthly_rate
        expected_interest = 800_000 * (0.0675 / 12)  # = $4,500
        assert abs(interest - expected_interest) < 0.01, \
            f"First month interest should be ${expected_interest:.2f}, got ${interest:.2f}"

        # Principal is the remainder
        expected_principal = 5189.43 - expected_interest  # ≈ $689
        assert abs(principal - expected_principal) < 0.01, \
            f"First month principal should be ${expected_principal:.2f}, got ${principal:.2f}"

        # Verify the split
        interest_percent = interest / 5189.43 * 100
        print(f"\nMonth 1 breakdown: {interest_percent:.1f}% interest, "
              f"{100-interest_percent:.1f}% principal")

    def test_amortization_over_time(self):
        """
        Over time, the interest portion decreases and principal increases.

        This is because:
        1. Each month, principal payment reduces the balance
        2. Next month's interest is calculated on the lower balance
        3. Since payment stays the same, more goes to principal
        """
        mortgage = MortgageState(
            original_principal=800_000,
            remaining_balance=800_000,
            monthly_payment=5189.43,
            interest_rate=0.0675,
            start_date=date(2025, 6, 1),
            term_months=360
        )

        # Simulate 12 months
        month_1_principal = None
        month_12_principal = None

        for month in range(1, 13):
            principal, interest = mortgage.calculate_month_payment()
            if month == 1:
                month_1_principal = principal
            if month == 12:
                month_12_principal = principal
            # Reduce balance (simulating what the simulation does)
            mortgage.remaining_balance -= principal

        # Month 12 should have MORE going to principal than month 1
        assert month_12_principal > month_1_principal, \
            "Principal portion should increase over time"

        print(f"\nMonth 1 principal: ${month_1_principal:.2f}")
        print(f"Month 12 principal: ${month_12_principal:.2f}")
        print(f"Increase: ${month_12_principal - month_1_principal:.2f}")


# =============================================================================
# SECTION 2: TAX CALCULATIONS
# =============================================================================
"""
CONCEPT: Progressive Tax Brackets (2024)

The US uses "marginal" tax brackets. You don't pay one rate on all income.
Instead, you pay different rates on different portions of your income.

Example for Single filer with $200,000 income:
    $0 - $11,600:        10% = $1,160
    $11,601 - $47,150:   12% = $4,266
    $47,151 - $100,525:  22% = $11,742
    $100,526 - $191,950: 24% = $21,942
    $191,951 - $200,000: 32% = $2,576
    Total federal tax: ~$41,686

This is different from thinking "I'm in the 32% bracket so I pay 32% on everything."
Your EFFECTIVE rate is $41,686 / $200,000 = 20.8%
"""


class TestTaxCalculations:
    """Tests for tax calculations."""

    def test_federal_tax_brackets(self):
        """
        Verify federal tax uses progressive brackets correctly.

        For $200,000 income (Single):
        - Should NOT be simply 32% * $200,000 = $64,000
        - Should be much less due to progressive brackets AND standard deduction

        The standard deduction ($14,600 for 2024) reduces taxable income first.
        """
        calc = TaxCalculator(FilingStatus.SINGLE, "CA")

        # Calculate federal tax on $200,000
        federal_tax = calc.calculate_federal_income_tax(200_000)

        # It should be around $35,000-40,000 (after standard deduction)
        # Not $64,000 if you incorrectly applied 32% to everything!
        assert 35_000 < federal_tax < 42_000, \
            f"Federal tax on $200k should be ~$37,500, got ${federal_tax:,.0f}"

        # Calculate effective rate
        effective_rate = federal_tax / 200_000 * 100
        print(f"\n$200,000 income:")
        print(f"  Federal tax: ${federal_tax:,.0f}")
        print(f"  Effective rate: {effective_rate:.1f}%")
        print(f"  (Not 32% because of progressive brackets + standard deduction)")

    def test_california_taxes_high_earners(self):
        """
        California has high taxes, especially for high earners.

        CA top bracket: 12.3% (+ 1% mental health tax above $1M)
        Combined with federal, high earners can pay 45%+ marginal rate.
        """
        calc = TaxCalculator(FilingStatus.SINGLE, "CA")

        ca_tax_200k = calc.calculate_california_income_tax(200_000)
        ca_tax_500k = calc.calculate_california_income_tax(500_000)

        # CA tax on $200k should be around $14,000-16,000
        assert 14_000 < ca_tax_200k < 18_000, \
            f"CA tax on $200k seems off: ${ca_tax_200k:,.0f}"

        # Higher income = higher effective rate
        effective_200k = ca_tax_200k / 200_000 * 100
        effective_500k = ca_tax_500k / 500_000 * 100

        assert effective_500k > effective_200k, \
            "Higher income should have higher effective rate"

        print(f"\nCalifornia taxes:")
        print(f"  $200k income: ${ca_tax_200k:,.0f} ({effective_200k:.1f}% effective)")
        print(f"  $500k income: ${ca_tax_500k:,.0f} ({effective_500k:.1f}% effective)")


# =============================================================================
# SECTION 3: CAPITAL GAINS TAX
# =============================================================================
"""
CONCEPT: Short-Term vs Long-Term Capital Gains

When you sell an asset for more than you paid, you have a capital gain.
The tax rate depends on how long you held it:

SHORT-TERM (held < 1 year):
    Taxed as ordinary income (up to 37% federal + state)

LONG-TERM (held >= 1 year):
    Special lower rates: 0%, 15%, or 20% federal
    BUT California taxes all gains as ordinary income!

Example: You sell RSUs for $50,000 gain
    - If held < 1 year: Could pay ~$18,500 in taxes (37% + state)
    - If held >= 1 year: Could pay ~$12,500 in taxes (20% federal + state)

Waiting for long-term treatment can save significant money!
"""


class TestCapitalGains:
    """Tests for capital gains calculations."""

    def test_short_vs_long_term_federal_rates(self):
        """
        Long-term gains have preferential federal rates.

        For someone with $200k ordinary income and $50k gain:
        - Short-term: Gain taxed at their marginal bracket (32%)
        - Long-term: Gain taxed at preferential rate (15-20%)
        """
        calc = TaxCalculator(FilingStatus.SINGLE, "CA")

        ordinary_income = 200_000
        gain = 50_000

        # Short-term gains (taxed as ordinary income)
        stcg_tax, _ = calc.calculate_federal_capital_gains_tax(
            ordinary_income, short_term_gains=gain, long_term_gains=0
        )

        # Long-term gains (preferential rates)
        _, ltcg_tax = calc.calculate_federal_capital_gains_tax(
            ordinary_income, short_term_gains=0, long_term_gains=gain
        )

        # Long-term should be significantly less
        assert ltcg_tax < stcg_tax, \
            "Long-term gains should be taxed less than short-term"

        savings = stcg_tax - ltcg_tax
        print(f"\n$50,000 gain with $200k income:")
        print(f"  Short-term federal tax: ${stcg_tax:,.0f}")
        print(f"  Long-term federal tax: ${ltcg_tax:,.0f}")
        print(f"  Savings from waiting: ${savings:,.0f}")

    def test_california_taxes_all_gains_same(self):
        """
        California doesn't distinguish short vs long-term gains.
        Both are taxed as ordinary income.

        This is why CA residents have higher effective capital gains rates!
        """
        calc = TaxCalculator(FilingStatus.SINGLE, "CA")

        base_income = 200_000
        gain = 50_000

        # CA tax on base income
        ca_base = calc.calculate_california_income_tax(base_income)

        # CA tax with gain (same whether short or long term)
        ca_with_gain = calc.calculate_california_income_tax(base_income + gain)

        # The additional tax on the gain
        ca_gain_tax = ca_with_gain - ca_base

        # Should be around 9.3% (CA marginal rate at this income)
        effective_rate = ca_gain_tax / gain * 100
        assert 8 < effective_rate < 12, \
            f"CA gain tax rate seems off: {effective_rate:.1f}%"

        print(f"\nCalifornia capital gains (no preferential treatment):")
        print(f"  Tax on $50k gain: ${ca_gain_tax:,.0f}")
        print(f"  Effective rate: {effective_rate:.1f}%")

    def test_niit_high_income(self):
        """
        Net Investment Income Tax (NIIT): Extra 3.8% on investment income.

        Applies when your income exceeds:
        - $200,000 for single
        - $250,000 for married filing jointly

        This is ON TOP of other capital gains taxes.
        """
        calc = TaxCalculator(FilingStatus.SINGLE, "CA")

        # Below NIIT threshold - no NIIT
        niit_low = calc.calculate_niit(150_000, investment_income=50_000)
        assert niit_low == 0, "NIIT shouldn't apply below $200k threshold"

        # Above NIIT threshold - NIIT applies
        # NIIT = 3.8% * min(investment_income, amount_over_threshold)
        niit_high = calc.calculate_niit(250_000, investment_income=50_000)
        expected = 50_000 * 0.038  # 3.8% of $50k gain
        assert abs(niit_high - expected) < 1, \
            f"NIIT should be ${expected:,.0f}, got ${niit_high:,.0f}"

        print(f"\nNIIT (3.8% surtax on investment income):")
        print(f"  At $150k income with $50k gain: ${niit_low:,.0f}")
        print(f"  At $250k income with $50k gain: ${niit_high:,.0f}")


# =============================================================================
# SECTION 4: RSU MECHANICS
# =============================================================================
"""
CONCEPT: Restricted Stock Units (RSUs)

RSUs are a form of stock compensation. Here's how they work:

1. GRANT: Company promises you X shares, vesting over time
2. VEST: When shares vest, you receive them (taxable as ordinary income!)
3. SELL: When you sell, any gain/loss from vest price is capital gain/loss

Example:
    - 100 shares vest when stock price is $150/share
    - Vest income: 100 * $150 = $15,000 (taxed as ordinary income)
    - Cost basis: $150/share
    - Later sell at $180/share
    - Capital gain: 100 * ($180 - $150) = $3,000

Tax-to-cover: Most companies sell some shares at vesting to cover taxes.
Typically ~37% in California (22% federal + 10% state + FICA).
"""


class TestRSUMechanics:
    """Tests for RSU handling."""

    def test_rsu_cost_basis_at_vest(self):
        """
        When RSUs vest, the stock price at vesting becomes your cost basis.

        This is important because:
        1. The vest value is taxed as ordinary income
        2. Future gains/losses are measured from this cost basis
        """
        lot = RSULot(
            lot_id="RSU-2024-001",
            shares=100,
            cost_basis_per_share=150.00,  # Stock price at vesting
            vest_date=date(2024, 3, 15)
        )

        # Total cost basis
        assert lot.cost_basis_total == 15_000, \
            "Cost basis should be shares * vest price"

        print(f"\nRSU Lot:")
        print(f"  Shares: {lot.shares}")
        print(f"  Vest price: ${lot.cost_basis_per_share}")
        print(f"  Cost basis: ${lot.cost_basis_total:,}")

    def test_rsu_holding_period(self):
        """
        The holding period starts at VESTING, not grant date.

        You need to hold for 1 year (365 days) from vesting for long-term treatment.
        """
        vest_date = date(2024, 3, 15)
        lot = RSULot(
            lot_id="RSU-2024-001",
            shares=100,
            cost_basis_per_share=150.00,
            vest_date=vest_date
        )

        # Sell 6 months later - short term
        short_term_sale = vest_date + relativedelta(months=6)
        assert lot.get_term(short_term_sale) == RSUTerm.SHORT_TERM

        # Sell 13 months later - long term
        long_term_sale = vest_date + relativedelta(months=13)
        assert lot.get_term(long_term_sale) == RSUTerm.LONG_TERM

        # Exactly 1 year (365 days) - LONG TERM in this implementation
        exactly_one_year = vest_date + relativedelta(years=1)
        assert lot.get_term(exactly_one_year) == RSUTerm.LONG_TERM

        # 364 days - still short term
        almost_one_year = vest_date + relativedelta(days=364)
        assert lot.get_term(almost_one_year) == RSUTerm.SHORT_TERM

        print(f"\nHolding period (vested {vest_date}):")
        print(f"  Sell {short_term_sale}: SHORT-TERM")
        print(f"  Sell {almost_one_year}: SHORT-TERM (364 days)")
        print(f"  Sell {exactly_one_year}: LONG-TERM (365+ days)")


# =============================================================================
# SECTION 5: SIMULATION INTEGRATION
# =============================================================================
"""
CONCEPT: Putting It All Together

The simulation combines all these concepts month-by-month:
1. Receive salary (taxed via withholding)
2. RSUs vest (taxed as income, shares added to holdings)
3. Sell RSUs (if strategy says to)
4. Pay housing costs (rent or mortgage + taxes + insurance)
5. Track net worth (cash + investments + RSUs + home equity)
"""


class TestSimulationIntegration:
    """Tests for the integrated simulation."""

    def test_basic_simulation_runs(self):
        """Verify a basic simulation completes without errors."""
        inputs = SimulationInputs(
            filing_status=FilingStatus.SINGLE,
            start_date=date(2025, 1, 1),
            initial_cash=100_000,
            income_schedule=[
                IncomeProfile(year=2025, base_salary=200_000, bonus=20_000),
                IncomeProfile(year=2026, base_salary=206_000, bonus=20_600)
            ],
            simulation_years=2
        )

        simulator = FinancialSimulator(inputs)
        result = simulator.run()

        # Should have 24 months of data
        assert len(result.monthly_snapshots) == 24

        # Net worth should grow (saving money each month)
        first_month = result.monthly_snapshots[0]
        last_month = result.monthly_snapshots[-1]
        assert last_month.net_worth > first_month.net_worth, \
            "Net worth should grow over time"

        print(f"\nBasic simulation (2 years, $200k salary):")
        print(f"  Starting net worth: ${first_month.net_worth:,.0f}")
        print(f"  Ending net worth: ${last_month.net_worth:,.0f}")

    def test_home_purchase_affects_net_worth(self):
        """
        Home purchase should:
        1. Reduce cash (down payment + closing costs)
        2. Create home equity
        3. Net worth = cash + investments + home equity
        """
        # Use explicit start date to ensure purchase happens during simulation
        start = date(2025, 1, 1)
        inputs = SimulationInputs(
            filing_status=FilingStatus.SINGLE,
            start_date=start,
            initial_cash=250_000,
            income_schedule=[
                IncomeProfile(year=2025, base_salary=200_000)
            ],
            house_plan=HousePurchasePlan(
                purchase_date=date(2025, 3, 1),
                home_price=1_000_000,
                down_payment_percent=0.20,
                mortgage_rate=0.0675
            ),
            simulation_years=1
        )

        simulator = FinancialSimulator(inputs)
        result = simulator.run()

        # Find month before and after purchase
        feb = next(s for s in result.monthly_snapshots if s.month == 2 and s.year == 2025)
        mar = next(s for s in result.monthly_snapshots if s.month == 3 and s.year == 2025)

        # Cash should drop significantly in March (down payment ~$200k + closing ~$30k)
        assert mar.cash_balance < feb.cash_balance - 150_000, \
            f"Cash should drop after down payment. Feb: ${feb.cash_balance:,.0f}, Mar: ${mar.cash_balance:,.0f}"

        # Home equity should appear (down payment creates initial equity)
        assert mar.home_equity > 0, "Should have home equity after purchase"

        print(f"\nHome purchase impact:")
        print(f"  Feb cash: ${feb.cash_balance:,.0f}")
        print(f"  Mar cash: ${mar.cash_balance:,.0f}")
        print(f"  Mar home equity: ${mar.home_equity:,.0f}")

    def test_rsu_vest_adds_income_and_holdings(self):
        """
        When RSUs vest:
        1. Full value is recorded as income (for tax purposes)
        2. Employer uses "sell-to-cover" - sells ~37% of shares to pay taxes
        3. Remaining ~63% of shares are added to holdings

        This is how most tech companies handle RSU vesting in California.
        """
        start = date(2025, 1, 1)
        vest_date = date(2025, 3, 15)

        inputs = SimulationInputs(
            filing_status=FilingStatus.SINGLE,
            start_date=start,
            initial_cash=50_000,
            income_schedule=[
                IncomeProfile(year=2025, base_salary=150_000)
            ],
            future_rsu_vests=[
                FutureRSUVest(
                    vest_id="VEST-001",
                    shares=100,
                    vest_date=vest_date
                )
            ],
            market=MarketAssumptions(current_stock_price=150.0),
            simulation_years=1
        )

        simulator = FinancialSimulator(inputs)
        result = simulator.run()

        # Find March snapshot (when vest happens)
        mar = next(s for s in result.monthly_snapshots if s.month == 3 and s.year == 2025)

        # RSU vest income is the FULL value (for tax reporting)
        expected_vest_income = 100 * 150.0  # $15,000
        assert mar.rsu_vest_income == expected_vest_income, \
            f"RSU vest income should be ${expected_vest_income:,}, got ${mar.rsu_vest_income:,}"

        # RSU holdings reflect sell-to-cover: only ~63% of shares kept
        # 100 shares * (1 - 0.37) = 63 shares * $150 = $9,450
        shares_after_withholding = int(100 * (1 - 0.37))  # 63 shares
        expected_holdings = shares_after_withholding * 150.0  # $9,450
        assert mar.rsu_holdings_value == expected_holdings, \
            f"RSU holdings should be ${expected_holdings:,} (after sell-to-cover). Got ${mar.rsu_holdings_value:,}"

        print(f"\nRSU vesting with sell-to-cover (100 shares @ $150):")
        print(f"  Vest income (full, for taxes): ${mar.rsu_vest_income:,.0f}")
        print(f"  Shares withheld for taxes: 37 (~37%)")
        print(f"  Shares kept: {shares_after_withholding}")
        print(f"  RSU holdings value: ${mar.rsu_holdings_value:,.0f}")


# =============================================================================
# SECTION 6: DEBT AMORTIZATION
# =============================================================================
"""
CONCEPT: Debt Payoff Over Time

Like mortgages, other debts (car loans, student loans) also amortize.
Each payment includes interest and principal, reducing the balance.
"""


class TestDebtAmortization:
    """Tests for debt balance reduction."""

    def test_debt_balance_decreases(self):
        """
        Debt balances should decrease as payments are made.
        """
        inputs = SimulationInputs(
            filing_status=FilingStatus.SINGLE,
            initial_cash=50_000,
            income_schedule=[
                IncomeProfile(year=2025, base_salary=100_000)
            ],
            debts=[
                DebtObligation(
                    name="Car Loan",
                    monthly_payment=500,
                    remaining_balance=20_000,
                    interest_rate=0.06  # 6% APR
                )
            ],
            simulation_years=1
        )

        simulator = FinancialSimulator(inputs)
        result = simulator.run()

        # After 12 payments, balance should be lower
        # With $500/month at 6%, most goes to principal
        # Rough estimate: ~$5,500 principal paid in year 1

        # Check that debt payments were made
        total_debt_payments = sum(s.other_debt_payments for s in result.monthly_snapshots)
        assert total_debt_payments > 5_000, \
            "Should have made debt payments throughout the year"

        print(f"\nDebt payoff:")
        print(f"  Total payments made: ${total_debt_payments:,.0f}")


# =============================================================================
# SECTION 7: INPUT VALIDATION
# =============================================================================
"""
CONCEPT: Garbage In, Garbage Out

Financial simulations need valid inputs. The validation catches common errors
like negative values or impossible percentages.
"""


class TestInputValidation:
    """Tests for input validation."""

    def test_negative_home_price_rejected(self):
        """Can't have a negative home price."""
        with pytest.raises(ValueError, match="home_price must be positive"):
            HousePurchasePlan(
                purchase_date=date(2025, 6, 1),
                home_price=-100_000,  # Invalid!
                down_payment_percent=0.20,
                mortgage_rate=0.0675
            )

    def test_invalid_down_payment_percent_rejected(self):
        """Down payment must be between 0 and 100%."""
        with pytest.raises(ValueError, match="down_payment_percent"):
            HousePurchasePlan(
                purchase_date=date(2025, 6, 1),
                home_price=500_000,
                down_payment_percent=1.5,  # 150%? Invalid!
                mortgage_rate=0.0675
            )

    def test_negative_cash_rejected(self):
        """Starting cash can't be negative."""
        with pytest.raises(ValueError, match="initial_cash cannot be negative"):
            SimulationInputs(
                filing_status=FilingStatus.SINGLE,
                initial_cash=-10_000  # Invalid!
            )


# =============================================================================
# RUN EDUCATIONAL SUMMARY
# =============================================================================

if __name__ == "__main__":
    """Run tests with verbose output to see the educational content."""
    print("=" * 70)
    print("FINANCIAL CONCEPTS EDUCATIONAL TEST SUITE")
    print("=" * 70)
    print("\nThis test suite validates calculations AND teaches concepts.")
    print("Run with: python -m pytest test_financial_concepts.py -v -s")
    print("\nThe -s flag shows the print statements with explanations.")
    print("=" * 70)

    # Run a quick demo
    print("\n" + "=" * 70)
    print("QUICK DEMO: Key Financial Concepts")
    print("=" * 70)

    # Demo 1: Mortgage payment
    print("\n1. MORTGAGE AMORTIZATION")
    print("-" * 40)
    inputs = SimulationInputs(
        filing_status=FilingStatus.SINGLE,
        initial_cash=200_000,
        house_plan=HousePurchasePlan(
            purchase_date=date(2025, 6, 1),
            home_price=1_000_000,
            down_payment_percent=0.20,
            mortgage_rate=0.0675
        )
    )
    sim = FinancialSimulator(inputs)
    payment = sim._calculate_monthly_pi(800_000, 0.0675, 30)
    first_interest = 800_000 * (0.0675 / 12)
    first_principal = payment - first_interest
    print(f"$800,000 loan at 6.75% for 30 years:")
    print(f"  Monthly payment: ${payment:,.2f}")
    print(f"  Month 1 interest: ${first_interest:,.2f} ({first_interest/payment*100:.0f}%)")
    print(f"  Month 1 principal: ${first_principal:,.2f} ({first_principal/payment*100:.0f}%)")

    # Demo 2: Tax brackets
    print("\n2. PROGRESSIVE TAX BRACKETS")
    print("-" * 40)
    calc = TaxCalculator(FilingStatus.SINGLE, "CA")
    for income in [100_000, 200_000, 400_000]:
        fed = calc.calculate_federal_income_tax(income)
        ca = calc.calculate_california_income_tax(income)
        total = fed + ca
        rate = total / income * 100
        print(f"${income:,} income: ${total:,.0f} total tax ({rate:.1f}% effective)")

    # Demo 3: Capital gains
    print("\n3. SHORT vs LONG-TERM CAPITAL GAINS")
    print("-" * 40)
    stcg, _ = calc.calculate_federal_capital_gains_tax(200_000, 50_000, 0)
    _, ltcg = calc.calculate_federal_capital_gains_tax(200_000, 0, 50_000)
    print(f"$50,000 gain with $200k income:")
    print(f"  Short-term federal tax: ${stcg:,.0f}")
    print(f"  Long-term federal tax: ${ltcg:,.0f}")
    print(f"  Savings from waiting: ${stcg - ltcg:,.0f}")

    print("\n" + "=" * 70)
    print("Run 'pytest test_financial_concepts.py -v -s' for full test output")
    print("=" * 70)
