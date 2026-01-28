#!/usr/bin/env python3
"""
Home Affordability Simulation - Example Usage

This script demonstrates how to use the unified financial simulation engine
to analyze home purchase decisions with multi-year projections.

The simulation takes into account:
- Multi-year income projections
- RSU holdings and future vesting schedule
- RSU selling strategies
- Investment accounts
- House purchase timing and terms
- Tax implications (Federal + California)
- Cash flow projections
- Net worth trajectory
- Breakeven analysis vs renting
"""

from datetime import date
from simulation_engine import (
    # Input structures
    SimulationInputs,
    IncomeProfile,
    RSULot,
    FutureRSUVest,
    RSUSellRule,
    RSUSellStrategy,
    InvestmentAccount,
    DebtObligation,
    HousePurchasePlan,
    MarketAssumptions,
    # Engine
    FinancialSimulator,
    # Output functions
    print_simulation_summary,
    print_monthly_detail,
    export_to_csv,
)
from config import FilingStatus, InvestmentType


def create_sample_inputs() -> SimulationInputs:
    """
    Create sample simulation inputs.

    Modify these values to match your personal situation.
    """

    # =========================================================================
    # INCOME SCHEDULE
    # =========================================================================
    # Project your income for the next several years
    income_schedule = [
        IncomeProfile(year=2025, base_salary=200000, bonus=20000),
        IncomeProfile(year=2026, base_salary=210000, bonus=25000),
        IncomeProfile(year=2027, base_salary=220000, bonus=30000),
        IncomeProfile(year=2028, base_salary=230000, bonus=30000),
        IncomeProfile(year=2029, base_salary=240000, bonus=35000),
        IncomeProfile(year=2030, base_salary=250000, bonus=40000),
    ]

    # =========================================================================
    # RSU HOLDINGS (Already Vested)
    # =========================================================================
    # These are RSUs you currently hold (already vested)
    rsu_holdings = [
        RSULot(
            lot_id="VEST-2023-Q1",
            shares=100,
            cost_basis_per_share=150.00,  # Price when it vested
            vest_date=date(2023, 3, 15)
        ),
        RSULot(
            lot_id="VEST-2023-Q3",
            shares=100,
            cost_basis_per_share=145.00,
            vest_date=date(2023, 9, 15)
        ),
        RSULot(
            lot_id="VEST-2024-Q1",
            shares=100,
            cost_basis_per_share=160.00,
            vest_date=date(2024, 3, 15)
        ),
        RSULot(
            lot_id="VEST-2024-Q3",
            shares=100,
            cost_basis_per_share=155.00,
            vest_date=date(2024, 9, 15)
        ),
    ]

    # =========================================================================
    # FUTURE RSU VESTS
    # =========================================================================
    # RSUs that will vest in the future
    future_rsu_vests = [
        FutureRSUVest(vest_id="VEST-2025-Q1", shares=100, vest_date=date(2025, 3, 15)),
        FutureRSUVest(vest_id="VEST-2025-Q3", shares=100, vest_date=date(2025, 9, 15)),
        FutureRSUVest(vest_id="VEST-2026-Q1", shares=100, vest_date=date(2026, 3, 15)),
        FutureRSUVest(vest_id="VEST-2026-Q3", shares=100, vest_date=date(2026, 9, 15)),
        FutureRSUVest(vest_id="VEST-2027-Q1", shares=75, vest_date=date(2027, 3, 15)),
        FutureRSUVest(vest_id="VEST-2027-Q3", shares=75, vest_date=date(2027, 9, 15)),
    ]

    # =========================================================================
    # RSU SELLING STRATEGY
    # =========================================================================
    # Define when to sell RSUs
    # Options:
    #   - SELL_IMMEDIATELY: Sell as soon as they vest
    #   - SELL_AT_PURCHASE: Sell to fund home purchase
    #   - SELL_LONG_TERM: Wait 1 year for long-term capital gains
    #   - HOLD: Don't sell
    #   - CUSTOM: Sell on specific date

    rsu_sell_rules = [
        # Sell existing holdings at home purchase time
        RSUSellRule(lot_id="VEST-2023-Q1", strategy=RSUSellStrategy.SELL_AT_PURCHASE),
        RSUSellRule(lot_id="VEST-2023-Q3", strategy=RSUSellStrategy.SELL_AT_PURCHASE),

        # Hold 2024 vests until they become long-term
        RSUSellRule(lot_id="VEST-2024-Q1", strategy=RSUSellStrategy.SELL_LONG_TERM),
        RSUSellRule(lot_id="VEST-2024-Q3", strategy=RSUSellStrategy.SELL_LONG_TERM),

        # Sell future vests immediately (to maximize liquidity)
        RSUSellRule(lot_id="all", strategy=RSUSellStrategy.SELL_IMMEDIATELY),
    ]

    # =========================================================================
    # INVESTMENT ACCOUNTS
    # =========================================================================
    investments = [
        InvestmentAccount(
            name="High-Yield Savings",
            account_type=InvestmentType.MONEY_MARKET,
            balance=50000,
            cost_basis=50000,
            annual_return=0.045,
            is_liquid=True
        ),
        InvestmentAccount(
            name="Brokerage - ETFs",
            account_type=InvestmentType.ETFS,
            balance=80000,
            cost_basis=60000,  # $20K unrealized gain
            annual_return=0.08,
            is_liquid=True
        ),
        InvestmentAccount(
            name="Bond Fund",
            account_type=InvestmentType.BONDS,
            balance=30000,
            cost_basis=28000,
            annual_return=0.04,
            is_liquid=True
        ),
    ]

    # =========================================================================
    # EXISTING DEBTS
    # =========================================================================
    debts = [
        DebtObligation(name="Car Loan", monthly_payment=450, remaining_balance=12000),
        DebtObligation(name="Student Loan", monthly_payment=300, remaining_balance=20000),
    ]

    # =========================================================================
    # HOUSE PURCHASE PLAN
    # =========================================================================
    house_plan = HousePurchasePlan(
        purchase_date=date(2025, 6, 1),
        home_price=1000000,
        down_payment_percent=0.20,  # 20% down
        mortgage_rate=0.0675,  # 6.75%
        loan_term_years=30,
        property_tax_rate=0.0125,  # 1.25% (California)
        hoa_monthly=400,
        homeowners_insurance_annual=2000,
        maintenance_rate=0.01  # 1% of home value annually
    )

    # =========================================================================
    # MARKET ASSUMPTIONS
    # =========================================================================
    market = MarketAssumptions(
        current_stock_price=170.00,
        stock_prices={
            date(2025, 1, 1): 170.00,
            date(2025, 6, 1): 175.00,
            date(2026, 1, 1): 180.00,
            date(2027, 1, 1): 190.00,
        },
        stock_annual_growth=0.08,  # 8% default growth
        home_appreciation_rate=0.03,  # 3% annually
        rent_increase_rate=0.04,  # 4% annually
        investment_return_rate=0.07,  # 7% for comparison
    )

    # =========================================================================
    # CREATE SIMULATION INPUTS
    # =========================================================================
    return SimulationInputs(
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        state="CA",
        start_date=date(2025, 1, 1),
        initial_cash=80000,
        income_schedule=income_schedule,
        rsu_holdings=rsu_holdings,
        future_rsu_vests=future_rsu_vests,
        rsu_sell_rules=rsu_sell_rules,
        stock_symbol="ACME",
        investments=investments,
        debts=debts,
        house_plan=house_plan,
        comparable_rent=4000,  # Monthly rent for similar property
        monthly_living_expenses=4000,  # Non-housing expenses
        market=market,
        simulation_years=10,
    )


def run_simulation():
    """Run the main simulation."""
    print("=" * 80)
    print("HOME AFFORDABILITY SIMULATION")
    print("=" * 80)

    # Create inputs
    inputs = create_sample_inputs()

    print("\nInitial Financial State:")
    print(f"  Cash: ${inputs.initial_cash:,.0f}")
    print(f"  Investments: ${sum(inv.balance for inv in inputs.investments):,.0f}")
    print(f"  RSU Holdings: {sum(lot.shares for lot in inputs.rsu_holdings)} shares")
    print(f"  Future RSU Vests: {sum(v.shares for v in inputs.future_rsu_vests)} shares")

    # Create and run simulator
    print("\nRunning simulation...")
    simulator = FinancialSimulator(inputs)
    result = simulator.run()

    # Print results
    print_simulation_summary(result)

    # Print first year detail
    print_monthly_detail(result, 2025)

    # Print year of purchase detail
    print_monthly_detail(result, 2026)

    return result


def run_scenario_comparison():
    """Compare different scenarios."""
    print("\n" + "=" * 80)
    print("SCENARIO COMPARISON")
    print("=" * 80)

    base_inputs = create_sample_inputs()

    scenarios = [
        ("Base: $1M, 20% down, 6.75%", base_inputs),
    ]

    # Scenario 2: Higher down payment
    inputs_25_down = create_sample_inputs()
    inputs_25_down.house_plan.down_payment_percent = 0.25
    scenarios.append(("25% down payment", inputs_25_down))

    # Scenario 3: Lower home price
    inputs_900k = create_sample_inputs()
    inputs_900k.house_plan.home_price = 900000
    scenarios.append(("$900K home", inputs_900k))

    # Scenario 4: Wait 1 year to buy
    inputs_wait = create_sample_inputs()
    inputs_wait.house_plan.purchase_date = date(2026, 6, 1)
    scenarios.append(("Wait 1 year to buy", inputs_wait))

    print(f"\n{'Scenario':<30} {'Final NW':>14} {'vs Rent':>14} {'Breakeven':>12}")
    print("-" * 72)

    for name, inputs in scenarios:
        simulator = FinancialSimulator(inputs)
        result = simulator.run()

        vs_rent = result.final_net_worth - result.rent_scenario_final_net_worth

        if result.breakeven_month:
            years = result.breakeven_month // 12
            months = result.breakeven_month % 12
            breakeven_str = f"{years}y {months}m"
        else:
            breakeven_str = "Never"

        print(
            f"{name:<30} "
            f"${result.final_net_worth:>12,.0f} "
            f"${vs_rent:>+12,.0f} "
            f"{breakeven_str:>12}"
        )


def analyze_rsu_strategy():
    """Analyze impact of different RSU selling strategies."""
    print("\n" + "=" * 80)
    print("RSU SELLING STRATEGY ANALYSIS")
    print("=" * 80)

    strategies = [
        ("Sell at purchase", RSUSellStrategy.SELL_AT_PURCHASE),
        ("Sell immediately", RSUSellStrategy.SELL_IMMEDIATELY),
        ("Wait for long-term", RSUSellStrategy.SELL_LONG_TERM),
        ("Hold all RSUs", RSUSellStrategy.HOLD),
    ]

    print(f"\n{'Strategy':<25} {'Final NW':>14} {'RSU Taxes':>14} {'Cash Flow Y1':>14}")
    print("-" * 70)

    for name, strategy in strategies:
        inputs = create_sample_inputs()
        inputs.rsu_sell_rules = [RSUSellRule(lot_id="all", strategy=strategy)]

        simulator = FinancialSimulator(inputs)
        result = simulator.run()

        y1_cash_flow = result.yearly_summaries[0].total_net_cash_flow

        print(
            f"{name:<25} "
            f"${result.final_net_worth:>12,.0f} "
            f"${result.total_rsu_taxes_paid:>12,.0f} "
            f"${y1_cash_flow:>12,.0f}"
        )


if __name__ == "__main__":
    # Run main simulation
    result = run_simulation()

    # Compare scenarios
    run_scenario_comparison()

    # Analyze RSU strategies
    analyze_rsu_strategy()

    # Export to CSV for further analysis
    export_to_csv(result, "simulation_results.csv")

    print("\n" + "=" * 80)
    print("SIMULATION COMPLETE")
    print("=" * 80)
    print("\nTo customize, modify the values in create_sample_inputs()")
    print("CSV exported to: simulation_results.csv")
