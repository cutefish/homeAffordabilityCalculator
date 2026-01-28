#!/usr/bin/env python3
"""
Example usage of the Home Affordability Calculator.

This script demonstrates how to set up and run the simulator
with sample data. Modify the values to match your situation.
"""

from datetime import date
from config import (
    SimulationConfig,
    FilingStatus,
    IncomeSchedule,
    RSUGrant,
    StockPriceProjection,
    Investment,
    InvestmentType,
    PropertyInputs,
    ClosingCostInputs,
    DebtItem
)
from simulator import (
    HomeAffordabilitySimulator,
    RSUSaleStrategy,
    print_scenario_summary
)
from affordability import compare_rent_vs_buy


def create_sample_config() -> SimulationConfig:
    """Create a sample configuration for demonstration."""

    # =========================================
    # INCOME SCHEDULE
    # =========================================
    # Projected annual income for upcoming years
    income_schedule = [
        IncomeSchedule(year=2024, gross_annual_income=200000, bonus=20000),
        IncomeSchedule(year=2025, gross_annual_income=210000, bonus=25000),
        IncomeSchedule(year=2026, gross_annual_income=220000, bonus=30000),
        IncomeSchedule(year=2027, gross_annual_income=230000, bonus=30000),
        IncomeSchedule(year=2028, gross_annual_income=240000, bonus=35000),
    ]

    # =========================================
    # RSU GRANTS
    # =========================================
    # Your RSU holdings - each row represents a vested lot
    rsu_grants = [
        RSUGrant(
            grant_id="RSU-001",
            quantity=100,
            cost_basis_per_share=150.00,  # Price at vesting
            vest_date=date(2023, 3, 15),
            grant_date=date(2022, 3, 15),
        ),
        RSUGrant(
            grant_id="RSU-002",
            quantity=150,
            cost_basis_per_share=140.00,
            vest_date=date(2023, 9, 15),
            grant_date=date(2022, 9, 15),
        ),
        RSUGrant(
            grant_id="RSU-003",
            quantity=100,
            cost_basis_per_share=160.00,
            vest_date=date(2024, 3, 15),
            grant_date=date(2023, 3, 15),
        ),
        RSUGrant(
            grant_id="RSU-004",
            quantity=150,
            cost_basis_per_share=155.00,
            vest_date=date(2024, 9, 15),
            grant_date=date(2023, 9, 15),
        ),
    ]

    # =========================================
    # STOCK PRICE PROJECTIONS
    # =========================================
    # Different scenarios for stock price
    stock_projections = [
        # Base case
        StockPriceProjection(date=date(2024, 6, 1), price=170.00, scenario="base"),
        StockPriceProjection(date=date(2024, 12, 1), price=175.00, scenario="base"),
        StockPriceProjection(date=date(2025, 6, 1), price=180.00, scenario="base"),

        # Optimistic case
        StockPriceProjection(date=date(2024, 6, 1), price=190.00, scenario="optimistic"),
        StockPriceProjection(date=date(2024, 12, 1), price=210.00, scenario="optimistic"),
        StockPriceProjection(date=date(2025, 6, 1), price=230.00, scenario="optimistic"),

        # Pessimistic case
        StockPriceProjection(date=date(2024, 6, 1), price=140.00, scenario="pessimistic"),
        StockPriceProjection(date=date(2024, 12, 1), price=130.00, scenario="pessimistic"),
        StockPriceProjection(date=date(2025, 6, 1), price=125.00, scenario="pessimistic"),
    ]

    # =========================================
    # OTHER INVESTMENTS
    # =========================================
    investments = [
        Investment(
            name="Money Market",
            investment_type=InvestmentType.MONEY_MARKET,
            current_value=50000,
            annual_return_rate=0.05,
            is_liquid=True
        ),
        Investment(
            name="12-Month CD",
            investment_type=InvestmentType.CD,
            current_value=30000,
            annual_return_rate=0.045,
            is_liquid=False,
            maturity_date=date(2025, 3, 1),
            early_withdrawal_penalty_months=3
        ),
        Investment(
            name="Managed Bond Fund",
            investment_type=InvestmentType.BONDS,
            current_value=40000,
            cost_basis=35000,
            annual_return_rate=0.04,
            is_liquid=True
        ),
        Investment(
            name="ETF Portfolio",
            investment_type=InvestmentType.ETFS,
            current_value=60000,
            cost_basis=45000,
            annual_return_rate=0.08,
            is_liquid=True
        ),
    ]

    # =========================================
    # EXISTING DEBTS
    # =========================================
    existing_debts = [
        DebtItem(
            name="Car Loan",
            monthly_payment=450,
            balance=15000,
            interest_rate=0.05
        ),
        DebtItem(
            name="Student Loan",
            monthly_payment=300,
            balance=25000,
            interest_rate=0.045
        ),
    ]

    # =========================================
    # PROPERTY INPUTS (Default/Template)
    # =========================================
    property_inputs = PropertyInputs(
        home_price=1000000,  # Will be varied in scenarios
        mortgage_rate=0.07,  # Will be varied in scenarios
        loan_term_years=30,
        down_payment_percent=0.20,
        property_tax_rate=0.0125,  # 1.25% for California
        hoa_monthly=400,
        homeowners_insurance_annual=2000,
        pmi_rate=0.005
    )

    # =========================================
    # CLOSING COST INPUTS
    # =========================================
    closing_cost_inputs = ClosingCostInputs(
        loan_origination_percent=0.01,
        appraisal_fee=600,
        title_insurance_percent=0.005,
        escrow_fee=2500,
        recording_fees=250,
        prepaid_property_tax_months=2,
        prepaid_insurance_months=12,
        other_fees=1500
    )

    # =========================================
    # CREATE CONFIG
    # =========================================
    return SimulationConfig(
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        state="CA",
        income_schedule=income_schedule,
        rsu_grants=rsu_grants,
        stock_symbol="ACME",
        stock_current_price=170.00,
        stock_projections=stock_projections,
        cash_savings=80000,
        investments=investments,
        existing_debts=existing_debts,
        property_inputs=property_inputs,
        closing_cost_inputs=closing_cost_inputs,
        target_purchase_date=date(2025, 6, 1)
    )


def run_basic_scenario():
    """Run a basic single scenario analysis."""
    print("\n" + "="*70)
    print("BASIC SCENARIO ANALYSIS")
    print("="*70)

    config = create_sample_config()
    simulator = HomeAffordabilitySimulator(config)

    # Define RSU sale strategy
    rsu_strategies = [
        RSUSaleStrategy(
            grant_id="RSU-001",
            shares_to_sell=100,
            target_sale_date=date(2025, 4, 1),
            target_price=175.00
        ),
        RSUSaleStrategy(
            grant_id="RSU-002",
            shares_to_sell=100,
            target_sale_date=date(2025, 4, 1),
            target_price=175.00
        ),
    ]

    # Investments to liquidate
    investments_to_liquidate = [
        ("Money Market", 40000),
        ("Managed Bond Fund", 20000),
    ]

    result = simulator.run_scenario(
        scenario_name="Base Case - $1M Home, 20% Down",
        home_price=1000000,
        down_payment_percent=0.20,
        mortgage_rate=0.07,
        stock_price=175.00,
        sale_year=2025,
        rsu_strategies=rsu_strategies,
        investments_to_liquidate=investments_to_liquidate,
        use_cash=60000,
        hoa_monthly=400
    )

    print_scenario_summary(result)


def run_multi_scenario_comparison():
    """Run multiple scenarios for comparison."""
    print("\n" + "="*70)
    print("MULTI-SCENARIO COMPARISON")
    print("="*70)

    config = create_sample_config()
    simulator = HomeAffordabilitySimulator(config)

    # RSU sale strategy (base)
    rsu_strategies = [
        RSUSaleStrategy(
            grant_id="RSU-001",
            shares_to_sell=100,
            target_sale_date=date(2025, 4, 1)
        ),
        RSUSaleStrategy(
            grant_id="RSU-002",
            shares_to_sell=150,
            target_sale_date=date(2025, 4, 1)
        ),
    ]

    investments_to_liquidate = [
        ("Money Market", 50000),
    ]

    result = simulator.run_multi_scenario_simulation(
        home_prices=[900000, 1000000, 1100000],
        down_payment_percents=[0.15, 0.20],
        mortgage_rates=[0.065, 0.070],
        stock_price_scenarios=[
            ("pessimistic", 130.00),
            ("base", 175.00),
            ("optimistic", 210.00),
        ],
        sale_year=2025,
        rsu_strategies=rsu_strategies,
        investments_to_liquidate=investments_to_liquidate,
        use_cash=50000,
        hoa_monthly=400
    )

    # Print summary of all scenarios
    print("\n--- SCENARIO COMPARISON SUMMARY ---\n")
    print(f"{'Scenario':<60} {'Monthly':<12} {'DTI':<10} {'Risk':<10}")
    print("-" * 92)

    for scenario in sorted(result.scenarios, key=lambda s: s.monthly_payment):
        print(
            f"{scenario.scenario_name:<60} "
            f"${scenario.monthly_payment:>9,.0f} "
            f"{scenario.affordability_metrics.back_end_dti*100:>7.1f}% "
            f"{scenario.affordability_metrics.risk_level:<10}"
        )

    print("\n--- RECOMMENDATIONS ---\n")
    for rec in result.recommendations:
        print(f"  - {rec}")


def run_rent_vs_buy_analysis():
    """Run rent vs buy comparison."""
    print("\n" + "="*70)
    print("RENT VS BUY ANALYSIS")
    print("="*70)

    property_inputs = PropertyInputs(
        home_price=1000000,
        mortgage_rate=0.07,
        loan_term_years=30,
        down_payment_percent=0.20,
        property_tax_rate=0.0125,
        hoa_monthly=400,
        homeowners_insurance_annual=2000
    )

    comparison = compare_rent_vs_buy(
        monthly_rent=3500,
        property_inputs=property_inputs,
        annual_income=220000,
        years=7,
        rent_increase_rate=0.04,
        home_appreciation_rate=0.03,
        investment_return_rate=0.07
    )

    print(f"\nComparison over {comparison['years_compared']} years:")

    print("\n--- RENTING ---")
    print(f"  Total rent paid: ${comparison['renting']['total_rent_paid']:,.0f}")
    print(f"  Final monthly rent: ${comparison['renting']['final_monthly_rent']:,.0f}")
    print(f"  Down payment invested value: ${comparison['renting']['investment_of_down_payment']:,.0f}")
    print(f"  Net cost of renting: ${comparison['renting']['net_cost']:,.0f}")

    print("\n--- BUYING ---")
    print(f"  Total payments made: ${comparison['buying']['total_payments']:,.0f}")
    print(f"  Principal paid: ${comparison['buying']['principal_paid']:,.0f}")
    print(f"  Interest paid: ${comparison['buying']['interest_paid']:,.0f}")
    print(f"  Home appreciation: ${comparison['buying']['home_appreciation']:,.0f}")
    print(f"  Equity built: ${comparison['buying']['equity_built']:,.0f}")
    print(f"  Net cost of buying: ${comparison['buying']['net_cost']:,.0f}")

    print("\n--- RECOMMENDATION ---")
    print(f"  {comparison['comparison']['breakeven_recommendation']} is better by "
          f"${abs(comparison['comparison']['buying_advantage']):,.0f}")


def analyze_rsu_timing():
    """Analyze impact of RSU sale timing."""
    print("\n" + "="*70)
    print("RSU TIMING ANALYSIS")
    print("="*70)

    config = create_sample_config()
    simulator = HomeAffordabilitySimulator(config)

    print("\nAnalyzing tax impact of selling RSUs at different times...\n")

    for grant in config.rsu_grants[:2]:
        print(f"\nGrant {grant.grant_id}:")
        print(f"  Quantity: {grant.quantity} shares")
        print(f"  Cost basis: ${grant.cost_basis_per_share:.2f}/share")
        print(f"  Vest date: {grant.vest_date}")

        # Check if already long-term
        today = date.today()
        term = grant.get_term(today)

        if term == config.RSUTerm.LONG_TERM:
            print(f"  Status: LONG-TERM eligible (held > 1 year)")
        else:
            lt_date = date(
                grant.vest_date.year + 1,
                grant.vest_date.month,
                grant.vest_date.day
            )
            print(f"  Status: SHORT-TERM until {lt_date}")

        # Calculate tax at different prices
        print(f"\n  Tax impact at different sale prices (income=$220K):")
        for price in [130, 150, 175, 200, 225]:
            result = simulator.tax_calc.calculate_rsu_sale_tax(
                grant=grant,
                sale_date=today,
                sale_price_per_share=price,
                ordinary_income=220000
            )
            print(f"    ${price}/share: Gain=${result.capital_gain:>10,.0f}, "
                  f"Tax=${result.federal_tax + result.state_tax + result.niit:>8,.0f}, "
                  f"Net=${result.net_proceeds:>10,.0f}")


if __name__ == "__main__":
    print("="*70)
    print("HOME AFFORDABILITY CALCULATOR - DEMONSTRATION")
    print("="*70)

    # Run different analyses
    run_basic_scenario()
    run_multi_scenario_comparison()
    run_rent_vs_buy_analysis()
    analyze_rsu_timing()

    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    print("\nTo customize this analysis, modify the values in create_sample_config()")
    print("and adjust the scenario parameters in each function.")
