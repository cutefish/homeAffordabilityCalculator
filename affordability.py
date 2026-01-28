"""
Affordability analyzer module.

Evaluates whether a home purchase is affordable based on:
- 28/36 rule
- Debt-to-income ratios
- Cash flow analysis
- Stress testing
"""

from dataclasses import dataclass
from typing import Optional
from config import (
    SimulationConfig,
    PropertyInputs,
    DebtItem,
    IncomeSchedule
)
from mortgage_calculator import MortgageCalculator, MonthlyPaymentBreakdown


@dataclass
class AffordabilityMetrics:
    """Key affordability metrics."""
    # DTI ratios
    front_end_dti: float  # Housing costs / gross income
    back_end_dti: float   # All debt / gross income

    # 28/36 rule compliance
    passes_28_rule: bool  # Front-end DTI <= 28%
    passes_36_rule: bool  # Back-end DTI <= 36%

    # Income multiples
    home_price_to_income_ratio: float
    loan_to_income_ratio: float

    # Monthly cash flow
    gross_monthly_income: float
    total_housing_cost: float
    total_debt_payments: float
    remaining_after_housing: float
    remaining_after_all_debt: float

    # Affordability scores
    affordability_score: float  # 0-100 score
    risk_level: str  # Low, Medium, High, Very High


@dataclass
class StressTestResult:
    """Results of stress testing."""
    scenario: str
    rate_increase: float
    new_monthly_payment: float
    new_front_end_dti: float
    new_back_end_dti: float
    still_affordable: bool


@dataclass
class CashFlowProjection:
    """Monthly cash flow projection."""
    month: int
    year: int
    gross_income: float
    housing_payment: float
    other_debt_payments: float
    estimated_taxes: float
    estimated_living_expenses: float
    net_cash_flow: float
    cumulative_savings: float


class AffordabilityAnalyzer:
    """Analyzer for home affordability."""

    # Standard DTI thresholds
    FRONT_END_THRESHOLD = 0.28  # Housing costs
    BACK_END_THRESHOLD = 0.36   # Total debt
    QUALIFIED_MORTGAGE_THRESHOLD = 0.43  # QM limit

    def __init__(
        self,
        property_inputs: PropertyInputs,
        annual_income: float,
        existing_debts: Optional[list[DebtItem]] = None
    ):
        self.property = property_inputs
        self.annual_income = annual_income
        self.monthly_income = annual_income / 12
        self.existing_debts = existing_debts or []

        self.mortgage_calc = MortgageCalculator(property_inputs)

    def calculate_dti_ratios(self) -> tuple[float, float]:
        """
        Calculate front-end and back-end DTI ratios.

        Returns:
            Tuple of (front_end_dti, back_end_dti)
        """
        monthly_breakdown = self.mortgage_calc.calculate_monthly_breakdown()
        housing_payment = monthly_breakdown.total_monthly

        other_debt_payments = sum(d.monthly_payment for d in self.existing_debts)

        front_end = housing_payment / self.monthly_income
        back_end = (housing_payment + other_debt_payments) / self.monthly_income

        return front_end, back_end

    def calculate_affordability_metrics(self) -> AffordabilityMetrics:
        """Calculate comprehensive affordability metrics."""
        monthly_breakdown = self.mortgage_calc.calculate_monthly_breakdown()
        housing_payment = monthly_breakdown.total_monthly

        other_debt_payments = sum(d.monthly_payment for d in self.existing_debts)
        total_debt = housing_payment + other_debt_payments

        front_end, back_end = self.calculate_dti_ratios()

        # Income ratios
        home_price_to_income = self.property.home_price / self.annual_income
        loan_to_income = self.property.loan_amount / self.annual_income

        # Cash flow
        remaining_after_housing = self.monthly_income - housing_payment
        remaining_after_debt = self.monthly_income - total_debt

        # Calculate affordability score (0-100)
        score = self._calculate_affordability_score(
            front_end, back_end, home_price_to_income
        )

        # Determine risk level
        risk_level = self._determine_risk_level(front_end, back_end)

        return AffordabilityMetrics(
            front_end_dti=front_end,
            back_end_dti=back_end,
            passes_28_rule=front_end <= self.FRONT_END_THRESHOLD,
            passes_36_rule=back_end <= self.BACK_END_THRESHOLD,
            home_price_to_income_ratio=home_price_to_income,
            loan_to_income_ratio=loan_to_income,
            gross_monthly_income=self.monthly_income,
            total_housing_cost=housing_payment,
            total_debt_payments=total_debt,
            remaining_after_housing=remaining_after_housing,
            remaining_after_all_debt=remaining_after_debt,
            affordability_score=score,
            risk_level=risk_level
        )

    def _calculate_affordability_score(
        self,
        front_end: float,
        back_end: float,
        price_to_income: float
    ) -> float:
        """
        Calculate affordability score from 0-100.

        Higher is better (more affordable).
        """
        score = 100.0

        # Deduct for front-end DTI
        if front_end > 0.20:
            score -= (front_end - 0.20) * 100
        if front_end > 0.28:
            score -= (front_end - 0.28) * 150

        # Deduct for back-end DTI
        if back_end > 0.30:
            score -= (back_end - 0.30) * 80
        if back_end > 0.36:
            score -= (back_end - 0.36) * 120

        # Deduct for high price-to-income ratio
        if price_to_income > 3:
            score -= (price_to_income - 3) * 10
        if price_to_income > 5:
            score -= (price_to_income - 5) * 15

        return max(0, min(100, score))

    def _determine_risk_level(
        self,
        front_end: float,
        back_end: float
    ) -> str:
        """Determine risk level based on DTI ratios."""
        if front_end <= 0.25 and back_end <= 0.33:
            return "Low"
        elif front_end <= 0.28 and back_end <= 0.36:
            return "Medium"
        elif front_end <= 0.33 and back_end <= 0.43:
            return "High"
        else:
            return "Very High"

    def stress_test(
        self,
        rate_increases: list[float] = [0.01, 0.02, 0.03]
    ) -> list[StressTestResult]:
        """
        Stress test affordability with higher interest rates.

        Useful for adjustable-rate mortgages or future refinancing.

        Args:
            rate_increases: List of rate increases to test (e.g., [0.01, 0.02])

        Returns:
            List of StressTestResult for each scenario
        """
        results = []
        original_rate = self.property.mortgage_rate

        for increase in rate_increases:
            new_rate = original_rate + increase

            # Calculate new payment
            new_payment = self.mortgage_calc.calculate_monthly_pi(
                annual_rate=new_rate
            )

            # Add non-P&I costs
            monthly_breakdown = self.mortgage_calc.calculate_monthly_breakdown()
            other_costs = (
                monthly_breakdown.property_tax
                + monthly_breakdown.homeowners_insurance
                + monthly_breakdown.pmi
                + monthly_breakdown.hoa
            )
            total_housing = new_payment + other_costs

            other_debt = sum(d.monthly_payment for d in self.existing_debts)

            new_front_end = total_housing / self.monthly_income
            new_back_end = (total_housing + other_debt) / self.monthly_income

            results.append(StressTestResult(
                scenario=f"+{increase*100:.1f}% rate increase",
                rate_increase=increase,
                new_monthly_payment=total_housing,
                new_front_end_dti=new_front_end,
                new_back_end_dti=new_back_end,
                still_affordable=new_back_end <= self.QUALIFIED_MORTGAGE_THRESHOLD
            ))

        return results

    def project_cash_flow(
        self,
        income_schedule: list[IncomeSchedule],
        years: int = 5,
        monthly_living_expenses: float = 3000,
        effective_tax_rate: float = 0.30,
        start_year: int = 2024
    ) -> list[CashFlowProjection]:
        """
        Project monthly cash flow over time.

        Args:
            income_schedule: List of annual income projections
            years: Number of years to project
            monthly_living_expenses: Estimated monthly living expenses
            effective_tax_rate: Effective income tax rate
            start_year: Starting year

        Returns:
            List of monthly CashFlowProjection
        """
        projections = []
        cumulative_savings = 0.0

        # Build income lookup
        income_by_year = {inc.year: inc.total_income for inc in income_schedule}

        # Get amortization schedule for housing payments
        amort = self.mortgage_calc.generate_amortization_schedule(years * 12)

        other_debt_payments = sum(d.monthly_payment for d in self.existing_debts)

        for month_idx in range(years * 12):
            year = start_year + (month_idx // 12)
            month = (month_idx % 12) + 1

            # Get income for this year
            annual_income = income_by_year.get(year, self.annual_income)
            gross_monthly = annual_income / 12

            # Get housing payment for this month
            if month_idx < len(amort):
                entry = amort[month_idx]
                housing_pi = entry.payment
                pmi = entry.pmi
            else:
                housing_pi = self.mortgage_calc.calculate_monthly_pi()
                pmi = 0

            monthly_breakdown = self.mortgage_calc.calculate_monthly_breakdown()
            housing_payment = (
                housing_pi
                + monthly_breakdown.property_tax
                + monthly_breakdown.homeowners_insurance
                + pmi
                + monthly_breakdown.hoa
            )

            # Estimate taxes
            estimated_taxes = gross_monthly * effective_tax_rate

            # Net cash flow
            net_cash_flow = (
                gross_monthly
                - housing_payment
                - other_debt_payments
                - estimated_taxes
                - monthly_living_expenses
            )

            cumulative_savings += net_cash_flow

            projections.append(CashFlowProjection(
                month=month,
                year=year,
                gross_income=gross_monthly,
                housing_payment=housing_payment,
                other_debt_payments=other_debt_payments,
                estimated_taxes=estimated_taxes,
                estimated_living_expenses=monthly_living_expenses,
                net_cash_flow=net_cash_flow,
                cumulative_savings=cumulative_savings
            ))

        return projections

    def calculate_max_affordable_price(
        self,
        target_front_end_dti: float = 0.28,
        target_back_end_dti: float = 0.36
    ) -> float:
        """
        Calculate maximum affordable home price.

        Args:
            target_front_end_dti: Target front-end DTI ratio
            target_back_end_dti: Target back-end DTI ratio

        Returns:
            Maximum affordable home price
        """
        from mortgage_calculator import calculate_max_home_price

        other_debt_payments = sum(d.monthly_payment for d in self.existing_debts)

        # Maximum total debt payment
        max_total_debt = self.monthly_income * target_back_end_dti
        max_housing_from_backend = max_total_debt - other_debt_payments

        # Maximum housing payment from front-end
        max_housing_from_frontend = self.monthly_income * target_front_end_dti

        # Use the more restrictive
        max_housing = min(max_housing_from_frontend, max_housing_from_backend)

        if max_housing <= 0:
            return 0.0

        # Calculate max home price
        return calculate_max_home_price(
            monthly_budget=max_housing,
            annual_rate=self.property.mortgage_rate,
            term_years=self.property.loan_term_years,
            down_payment_percent=self.property.down_payment / self.property.home_price
            if self.property.down_payment_amount else self.property.down_payment_percent,
            property_tax_rate=self.property.property_tax_rate,
            insurance_annual=self.property.homeowners_insurance_annual,
            hoa_monthly=self.property.hoa_monthly,
            include_pmi=self.property.requires_pmi,
            pmi_rate=self.property.pmi_rate
        )


def compare_rent_vs_buy(
    monthly_rent: float,
    property_inputs: PropertyInputs,
    annual_income: float,
    years: int = 7,
    rent_increase_rate: float = 0.03,
    home_appreciation_rate: float = 0.03,
    investment_return_rate: float = 0.07
) -> dict:
    """
    Compare renting vs buying over time.

    Args:
        monthly_rent: Current monthly rent
        property_inputs: Property purchase details
        annual_income: Annual gross income
        years: Number of years to compare
        rent_increase_rate: Annual rent increase rate
        home_appreciation_rate: Annual home value appreciation
        investment_return_rate: Return rate if down payment invested instead

    Returns:
        Dictionary with comparison results
    """
    mortgage_calc = MortgageCalculator(property_inputs)
    amort = mortgage_calc.generate_amortization_schedule(years * 12)
    monthly_breakdown = mortgage_calc.calculate_monthly_breakdown()

    # Renting costs
    total_rent_paid = 0.0
    current_rent = monthly_rent

    for year in range(years):
        annual_rent = current_rent * 12
        total_rent_paid += annual_rent
        current_rent *= (1 + rent_increase_rate)

    # What if down payment was invested?
    down_payment = property_inputs.down_payment
    investment_value = down_payment * ((1 + investment_return_rate) ** years)
    investment_gain = investment_value - down_payment

    # Buying costs
    housing_payments = sum(
        entry.payment + entry.pmi +
        monthly_breakdown.property_tax +
        monthly_breakdown.homeowners_insurance +
        monthly_breakdown.hoa
        for entry in amort
    )

    interest_paid = sum(entry.interest for entry in amort)
    principal_paid = sum(entry.principal for entry in amort)
    pmi_paid = sum(entry.pmi for entry in amort)

    # Home value after appreciation
    final_home_value = property_inputs.home_price * ((1 + home_appreciation_rate) ** years)
    home_appreciation = final_home_value - property_inputs.home_price

    # Remaining loan balance
    remaining_balance = amort[-1].remaining_balance if amort else property_inputs.loan_amount

    # Equity at end
    equity = final_home_value - remaining_balance

    # Net cost of buying
    # (payments made + opportunity cost) - (equity gained + tax benefits)
    # Simplified: we ignore tax benefits for now
    closing_costs_estimate = property_inputs.loan_amount * 0.03
    selling_costs_estimate = final_home_value * 0.06  # Agent fees, etc.

    net_cost_buying = (
        housing_payments
        + closing_costs_estimate
        + selling_costs_estimate
        + down_payment
        - equity
    )

    # Net cost of renting
    net_cost_renting = total_rent_paid - investment_gain

    return {
        'years_compared': years,
        'renting': {
            'total_rent_paid': total_rent_paid,
            'final_monthly_rent': current_rent / (1 + rent_increase_rate),
            'investment_of_down_payment': investment_value,
            'net_cost': net_cost_renting
        },
        'buying': {
            'total_payments': housing_payments,
            'principal_paid': principal_paid,
            'interest_paid': interest_paid,
            'pmi_paid': pmi_paid,
            'closing_costs': closing_costs_estimate,
            'selling_costs': selling_costs_estimate,
            'home_appreciation': home_appreciation,
            'final_home_value': final_home_value,
            'remaining_balance': remaining_balance,
            'equity_built': equity,
            'net_cost': net_cost_buying
        },
        'comparison': {
            'buying_advantage': net_cost_renting - net_cost_buying,
            'breakeven_recommendation': 'Buy' if net_cost_buying < net_cost_renting else 'Rent'
        }
    }
