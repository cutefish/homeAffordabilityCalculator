#!/usr/bin/env python3
"""Basic tests to validate the calculator works."""

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
from tax_calculator import TaxCalculator, RSUTerm
from mortgage_calculator import MortgageCalculator
from closing_costs import ClosingCostCalculator
from affordability import AffordabilityAnalyzer


def test_tax_calculator():
    """Test the tax calculator."""
    print("Testing TaxCalculator...")

    calc = TaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, "CA")

    # Test federal income tax
    fed_tax = calc.calculate_federal_income_tax(200000)
    print(f"  Federal tax on $200K income: ${fed_tax:,.0f}")
    assert fed_tax > 0, "Federal tax should be positive"

    # Test California tax
    ca_tax = calc.calculate_california_income_tax(200000)
    print(f"  CA tax on $200K income: ${ca_tax:,.0f}")
    assert ca_tax > 0, "CA tax should be positive"

    # Test capital gains
    stcg, ltcg = calc.calculate_federal_capital_gains_tax(
        ordinary_income=200000,
        short_term_gains=50000,
        long_term_gains=50000
    )
    print(f"  STCG tax on $50K: ${stcg:,.0f}")
    print(f"  LTCG tax on $50K: ${ltcg:,.0f}")
    assert stcg > ltcg, "Short-term gains should be taxed higher"

    print("  TaxCalculator tests PASSED")


def test_mortgage_calculator():
    """Test the mortgage calculator."""
    print("Testing MortgageCalculator...")

    prop = PropertyInputs(
        home_price=1000000,
        mortgage_rate=0.07,
        loan_term_years=30,
        down_payment_percent=0.20,
        property_tax_rate=0.0125,
        hoa_monthly=400,
        homeowners_insurance_annual=2000
    )

    calc = MortgageCalculator(prop)

    # Test monthly payment
    monthly_pi = calc.calculate_monthly_pi()
    print(f"  Monthly P&I on $800K at 7%: ${monthly_pi:,.0f}")
    assert 5000 < monthly_pi < 6000, f"Monthly payment ${monthly_pi} seems off"

    # Test breakdown
    breakdown = calc.calculate_monthly_breakdown()
    print(f"  Monthly property tax: ${breakdown.property_tax:,.0f}")
    print(f"  Monthly insurance: ${breakdown.homeowners_insurance:,.0f}")
    print(f"  Monthly HOA: ${breakdown.hoa:,.0f}")
    print(f"  Total monthly: ${breakdown.total_monthly:,.0f}")

    # Test amortization
    schedule = calc.generate_amortization_schedule(12)
    print(f"  First month principal: ${schedule[0].principal:,.0f}")
    print(f"  First month interest: ${schedule[0].interest:,.0f}")
    assert len(schedule) == 12, "Should have 12 months of schedule"

    # Test summary
    summary = calc.calculate_mortgage_summary()
    print(f"  Total interest over loan: ${summary.total_interest_paid:,.0f}")
    assert summary.total_interest_paid > prop.loan_amount, "Interest should exceed principal for 30yr"

    print("  MortgageCalculator tests PASSED")


def test_closing_costs():
    """Test the closing costs calculator."""
    print("Testing ClosingCostCalculator...")

    prop = PropertyInputs(
        home_price=1000000,
        mortgage_rate=0.07,
        down_payment_percent=0.20
    )

    closing_inputs = ClosingCostInputs()

    calc = ClosingCostCalculator(prop, closing_inputs)

    costs = calc.calculate_closing_costs()
    print(f"  Loan costs: ${costs.total_loan_costs:,.0f}")
    print(f"  Title/escrow: ${costs.total_title_escrow:,.0f}")
    print(f"  Prepaids: ${costs.total_prepaids:,.0f}")
    print(f"  Total closing: ${costs.total_closing_costs:,.0f}")

    # Should be roughly 2-5% of loan
    loan = prop.loan_amount
    assert loan * 0.01 < costs.total_closing_costs < loan * 0.06, "Closing costs seem off"

    print("  ClosingCostCalculator tests PASSED")


def test_affordability():
    """Test the affordability analyzer."""
    print("Testing AffordabilityAnalyzer...")

    prop = PropertyInputs(
        home_price=800000,
        mortgage_rate=0.07,
        down_payment_percent=0.20,
        property_tax_rate=0.0125,
        hoa_monthly=300
    )

    analyzer = AffordabilityAnalyzer(
        property_inputs=prop,
        annual_income=200000,
        existing_debts=[DebtItem(name="Car", monthly_payment=400)]
    )

    metrics = analyzer.calculate_affordability_metrics()
    print(f"  Front-end DTI: {metrics.front_end_dti*100:.1f}%")
    print(f"  Back-end DTI: {metrics.back_end_dti*100:.1f}%")
    print(f"  Passes 28/36: {metrics.passes_28_rule}/{metrics.passes_36_rule}")
    print(f"  Risk level: {metrics.risk_level}")

    # Stress test
    stress = analyzer.stress_test([0.01, 0.02])
    print(f"  Stress test +1%: DTI={stress[0].new_back_end_dti*100:.1f}%")
    print(f"  Stress test +2%: DTI={stress[1].new_back_end_dti*100:.1f}%")

    print("  AffordabilityAnalyzer tests PASSED")


def test_rsu_sale():
    """Test RSU sale tax calculations."""
    print("Testing RSU sale calculations...")

    calc = TaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, "CA")

    grant = RSUGrant(
        grant_id="TEST-001",
        quantity=100,
        cost_basis_per_share=150.00,
        vest_date=date(2023, 1, 15)
    )

    # Long-term sale (more than 1 year after vest)
    lt_result = calc.calculate_rsu_sale_tax(
        grant=grant,
        sale_date=date(2024, 6, 1),
        sale_price_per_share=200.00,
        ordinary_income=200000
    )

    print(f"  Long-term sale:")
    print(f"    Gross proceeds: ${lt_result.gross_proceeds:,.0f}")
    print(f"    Capital gain: ${lt_result.capital_gain:,.0f}")
    print(f"    Term: {lt_result.term}")
    print(f"    Federal tax: ${lt_result.federal_tax:,.0f}")
    print(f"    State tax: ${lt_result.state_tax:,.0f}")
    print(f"    Net proceeds: ${lt_result.net_proceeds:,.0f}")

    assert lt_result.term == RSUTerm.LONG_TERM, "Should be long-term"
    assert lt_result.capital_gain == 5000, "Gain should be $5000"

    print("  RSU sale tests PASSED")


if __name__ == "__main__":
    print("=" * 50)
    print("RUNNING BASIC VALIDATION TESTS")
    print("=" * 50)

    test_tax_calculator()
    test_mortgage_calculator()
    test_closing_costs()
    test_affordability()
    test_rsu_sale()

    print("\n" + "=" * 50)
    print("ALL TESTS PASSED!")
    print("=" * 50)
