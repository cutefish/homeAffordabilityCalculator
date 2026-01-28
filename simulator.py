"""
Home Affordability Simulator.

Main simulation engine that combines all modules to provide
comprehensive analysis of home buying scenarios.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from config import (
    SimulationConfig,
    RSUGrant,
    RSUTerm,
    StockPriceProjection,
    Investment,
    InvestmentType,
    FilingStatus,
    PropertyInputs
)
from tax_calculator import TaxCalculator, RSUSaleResult
from mortgage_calculator import MortgageCalculator, MortgageSummary
from closing_costs import ClosingCostCalculator, TotalCashNeeded, ClosingCostBreakdown
from affordability import AffordabilityAnalyzer, AffordabilityMetrics


@dataclass
class RSUSaleStrategy:
    """Strategy for selling RSUs."""
    grant_id: str
    shares_to_sell: int
    target_sale_date: date
    target_price: Optional[float] = None  # If None, use projected price


@dataclass
class DownPaymentSource:
    """Source of funds for down payment."""
    source_name: str
    amount: float
    tax_impact: float  # Tax owed from liquidating this source
    net_amount: float  # Amount after taxes

    @property
    def effective_rate(self) -> float:
        """Effective cost rate (taxes as % of gross)."""
        if self.amount == 0:
            return 0.0
        return self.tax_impact / self.amount


@dataclass
class DownPaymentPlan:
    """Plan for funding the down payment."""
    total_needed: float
    sources: list[DownPaymentSource]
    total_gross: float
    total_tax_impact: float
    total_net: float
    shortfall: float


@dataclass
class ScenarioResult:
    """Results for a single simulation scenario."""
    scenario_name: str
    home_price: float
    down_payment_percent: float
    mortgage_rate: float
    stock_price: float

    # Down payment analysis
    down_payment_plan: DownPaymentPlan

    # Mortgage analysis
    mortgage_summary: MortgageSummary

    # Closing costs
    closing_costs: ClosingCostBreakdown
    total_cash_needed: TotalCashNeeded

    # Affordability
    affordability_metrics: AffordabilityMetrics

    # Tax analysis (first year)
    first_year_tax_impact: float
    mortgage_interest_deduction: float

    # Summary metrics
    total_upfront_cost: float
    monthly_payment: float
    effective_monthly_cost: float  # After tax benefits


@dataclass
class SimulationResult:
    """Complete simulation results."""
    config: SimulationConfig
    scenarios: list[ScenarioResult]
    rsu_sale_details: list[RSUSaleResult]
    recommendations: list[str]


class HomeAffordabilitySimulator:
    """Main simulator for home affordability analysis."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.tax_calc = TaxCalculator(
            filing_status=config.filing_status,
            state=config.state
        )

    def calculate_rsu_sale_proceeds(
        self,
        strategies: list[RSUSaleStrategy],
        sale_year_income: float
    ) -> tuple[list[RSUSaleResult], float, float]:
        """
        Calculate proceeds from RSU sales.

        Args:
            strategies: List of RSU sale strategies
            sale_year_income: Ordinary income for the sale year

        Returns:
            Tuple of (sale_results, total_gross, total_net)
        """
        results = []
        total_gross = 0.0
        total_net = 0.0

        # Track cumulative gains for proper tax calculation
        cumulative_short_term = 0.0
        cumulative_long_term = 0.0

        for strategy in strategies:
            # Find the grant
            grant = next(
                (g for g in self.config.rsu_grants if g.grant_id == strategy.grant_id),
                None
            )
            if grant is None:
                continue

            # Determine sale price
            if strategy.target_price is not None:
                sale_price = strategy.target_price
            else:
                sale_price = self.config.get_stock_price_on_date(
                    strategy.target_sale_date
                )

            # Calculate tax on this sale
            result = self.tax_calc.calculate_rsu_sale_tax(
                grant=grant,
                sale_date=strategy.target_sale_date,
                sale_price_per_share=sale_price,
                ordinary_income=sale_year_income + cumulative_short_term,
                shares_to_sell=strategy.shares_to_sell
            )

            results.append(result)
            total_gross += result.gross_proceeds
            total_net += result.net_proceeds

            # Update cumulative gains
            if result.term == RSUTerm.SHORT_TERM:
                cumulative_short_term += max(0, result.capital_gain)
            else:
                cumulative_long_term += max(0, result.capital_gain)

        return results, total_gross, total_net

    def calculate_investment_liquidation(
        self,
        investments_to_liquidate: list[tuple[str, float]],
        sale_year_income: float
    ) -> list[DownPaymentSource]:
        """
        Calculate proceeds from liquidating investments.

        Args:
            investments_to_liquidate: List of (investment_name, amount_to_liquidate)
            sale_year_income: Ordinary income for tax calculation

        Returns:
            List of DownPaymentSource for each liquidation
        """
        sources = []

        for inv_name, amount in investments_to_liquidate:
            # Find the investment
            investment = next(
                (i for i in self.config.investments if i.name == inv_name),
                None
            )
            if investment is None:
                continue

            # Calculate tax impact based on investment type
            if investment.investment_type == InvestmentType.MONEY_MARKET:
                # Interest taxed as ordinary income (but already received)
                tax_impact = 0.0
                net_amount = amount

            elif investment.investment_type == InvestmentType.CD:
                # Check for early withdrawal penalty
                penalty = 0.0
                if (investment.maturity_date and
                    date.today() < investment.maturity_date):
                    penalty = investment.calculate_early_withdrawal_penalty()
                    penalty = penalty * (amount / investment.current_value)

                # Interest taxed as ordinary income
                tax_impact = penalty
                net_amount = amount - penalty

            else:
                # Calculate capital gains tax
                proportion = amount / investment.current_value
                gain = investment.unrealized_gain * proportion

                if gain > 0:
                    # Assume long-term for managed accounts
                    _, ltcg_tax = self.tax_calc.calculate_federal_capital_gains_tax(
                        ordinary_income=sale_year_income,
                        short_term_gains=0,
                        long_term_gains=gain
                    )
                    niit = self.tax_calc.calculate_niit(sale_year_income, gain)
                    state_tax = self.tax_calc.calculate_california_income_tax(
                        sale_year_income + gain
                    ) - self.tax_calc.calculate_california_income_tax(sale_year_income)

                    tax_impact = ltcg_tax + niit + state_tax
                else:
                    tax_impact = 0.0

                net_amount = amount - tax_impact

            sources.append(DownPaymentSource(
                source_name=inv_name,
                amount=amount,
                tax_impact=tax_impact,
                net_amount=net_amount
            ))

        return sources

    def create_down_payment_plan(
        self,
        target_amount: float,
        rsu_strategies: list[RSUSaleStrategy],
        investments_to_liquidate: list[tuple[str, float]],
        use_cash: float,
        sale_year_income: float
    ) -> DownPaymentPlan:
        """
        Create a comprehensive down payment funding plan.

        Args:
            target_amount: Total down payment needed
            rsu_strategies: RSU sale strategies
            investments_to_liquidate: Investment liquidations
            use_cash: Cash savings to use
            sale_year_income: Income for tax calculation

        Returns:
            DownPaymentPlan with all sources
        """
        sources = []

        # Add cash (no tax impact)
        if use_cash > 0:
            sources.append(DownPaymentSource(
                source_name="Cash Savings",
                amount=use_cash,
                tax_impact=0.0,
                net_amount=use_cash
            ))

        # Add RSU proceeds
        if rsu_strategies:
            rsu_results, rsu_gross, rsu_net = self.calculate_rsu_sale_proceeds(
                rsu_strategies, sale_year_income
            )
            total_rsu_tax = rsu_gross - rsu_net
            sources.append(DownPaymentSource(
                source_name="RSU Sales",
                amount=rsu_gross,
                tax_impact=total_rsu_tax,
                net_amount=rsu_net
            ))

        # Add investment liquidations
        inv_sources = self.calculate_investment_liquidation(
            investments_to_liquidate, sale_year_income
        )
        sources.extend(inv_sources)

        # Calculate totals
        total_gross = sum(s.amount for s in sources)
        total_tax = sum(s.tax_impact for s in sources)
        total_net = sum(s.net_amount for s in sources)
        shortfall = max(0, target_amount - total_net)

        return DownPaymentPlan(
            total_needed=target_amount,
            sources=sources,
            total_gross=total_gross,
            total_tax_impact=total_tax,
            total_net=total_net,
            shortfall=shortfall
        )

    def run_scenario(
        self,
        scenario_name: str,
        home_price: float,
        down_payment_percent: float,
        mortgage_rate: float,
        stock_price: float,
        sale_year: int,
        rsu_strategies: list[RSUSaleStrategy],
        investments_to_liquidate: list[tuple[str, float]],
        use_cash: float,
        hoa_monthly: float = 0.0
    ) -> ScenarioResult:
        """
        Run a single simulation scenario.

        Args:
            scenario_name: Name for this scenario
            home_price: Home purchase price
            down_payment_percent: Down payment as decimal
            mortgage_rate: Annual mortgage rate
            stock_price: Stock price assumption for RSUs
            sale_year: Year of purchase (for income lookup)
            rsu_strategies: RSU sale strategies
            investments_to_liquidate: Investment liquidations
            use_cash: Cash to use for down payment
            hoa_monthly: Monthly HOA fees

        Returns:
            ScenarioResult with complete analysis
        """
        # Get income for the sale year
        income_schedule = self.config.get_income_for_year(sale_year)
        annual_income = (
            income_schedule.total_income if income_schedule
            else self.config.income_schedule[0].total_income
        )

        # Create property inputs
        property_inputs = PropertyInputs(
            home_price=home_price,
            mortgage_rate=mortgage_rate,
            loan_term_years=self.config.property_inputs.loan_term_years,
            down_payment_percent=down_payment_percent,
            property_tax_rate=self.config.property_inputs.property_tax_rate,
            hoa_monthly=hoa_monthly,
            homeowners_insurance_annual=self.config.property_inputs.homeowners_insurance_annual,
            pmi_rate=self.config.property_inputs.pmi_rate
        )

        # Calculate down payment plan
        down_payment_amount = home_price * down_payment_percent
        down_payment_plan = self.create_down_payment_plan(
            target_amount=down_payment_amount,
            rsu_strategies=rsu_strategies,
            investments_to_liquidate=investments_to_liquidate,
            use_cash=use_cash,
            sale_year_income=annual_income
        )

        # Calculate mortgage details
        mortgage_calc = MortgageCalculator(property_inputs)
        mortgage_summary = mortgage_calc.calculate_mortgage_summary()

        # Calculate closing costs
        closing_calc = ClosingCostCalculator(
            property_inputs,
            self.config.closing_cost_inputs
        )
        closing_costs = closing_calc.calculate_closing_costs()
        total_cash_needed = closing_calc.calculate_total_cash_needed()

        # Calculate affordability
        affordability = AffordabilityAnalyzer(
            property_inputs=property_inputs,
            annual_income=annual_income,
            existing_debts=self.config.existing_debts
        )
        affordability_metrics = affordability.calculate_affordability_metrics()

        # Calculate first year tax impact
        first_year_interest = mortgage_calc.calculate_interest_paid_in_year(1)
        first_year_property_tax = home_price * property_inputs.property_tax_rate

        # Tax benefit from itemized deductions
        # SALT capped at $10k
        salt_deduction = min(first_year_property_tax, 10000)
        potential_itemized = first_year_interest + salt_deduction

        # Compare to standard deduction
        from tax_calculator import STANDARD_DEDUCTION_2024
        standard = STANDARD_DEDUCTION_2024[self.config.filing_status]

        if potential_itemized > standard:
            marginal_rate = 0.35  # Approximate for high earners in CA
            tax_benefit = (potential_itemized - standard) * marginal_rate
            mortgage_interest_deduction = first_year_interest
        else:
            tax_benefit = 0.0
            mortgage_interest_deduction = 0.0

        # Calculate total upfront cost
        total_upfront = (
            down_payment_amount
            + closing_costs.total_closing_costs
            + down_payment_plan.total_tax_impact
        )

        # Monthly payment
        monthly_breakdown = mortgage_calc.calculate_monthly_breakdown()
        monthly_payment = monthly_breakdown.total_monthly

        # Effective monthly cost after tax benefits
        monthly_tax_benefit = tax_benefit / 12
        effective_monthly = monthly_payment - monthly_tax_benefit

        return ScenarioResult(
            scenario_name=scenario_name,
            home_price=home_price,
            down_payment_percent=down_payment_percent,
            mortgage_rate=mortgage_rate,
            stock_price=stock_price,
            down_payment_plan=down_payment_plan,
            mortgage_summary=mortgage_summary,
            closing_costs=closing_costs,
            total_cash_needed=total_cash_needed,
            affordability_metrics=affordability_metrics,
            first_year_tax_impact=down_payment_plan.total_tax_impact,
            mortgage_interest_deduction=mortgage_interest_deduction,
            total_upfront_cost=total_upfront,
            monthly_payment=monthly_payment,
            effective_monthly_cost=effective_monthly
        )

    def run_multi_scenario_simulation(
        self,
        home_prices: list[float],
        down_payment_percents: list[float],
        mortgage_rates: list[float],
        stock_price_scenarios: list[tuple[str, float]],
        sale_year: int,
        rsu_strategies: list[RSUSaleStrategy],
        investments_to_liquidate: list[tuple[str, float]],
        use_cash: float,
        hoa_monthly: float = 0.0
    ) -> SimulationResult:
        """
        Run multiple scenarios for comparison.

        Args:
            home_prices: List of home prices to test
            down_payment_percents: List of down payment percentages
            mortgage_rates: List of mortgage rates
            stock_price_scenarios: List of (name, price) tuples
            sale_year: Year of purchase
            rsu_strategies: RSU sale strategies (base)
            investments_to_liquidate: Investment liquidations
            use_cash: Cash to use
            hoa_monthly: Monthly HOA

        Returns:
            SimulationResult with all scenarios
        """
        scenarios = []
        all_rsu_results = []

        for home_price in home_prices:
            for dp_pct in down_payment_percents:
                for rate in mortgage_rates:
                    for stock_name, stock_price in stock_price_scenarios:
                        # Update RSU strategies with this stock price
                        updated_strategies = [
                            RSUSaleStrategy(
                                grant_id=s.grant_id,
                                shares_to_sell=s.shares_to_sell,
                                target_sale_date=s.target_sale_date,
                                target_price=stock_price
                            )
                            for s in rsu_strategies
                        ]

                        scenario_name = (
                            f"${home_price/1000:.0f}K home, "
                            f"{dp_pct*100:.0f}% down, "
                            f"{rate*100:.2f}% rate, "
                            f"{stock_name} stock"
                        )

                        result = self.run_scenario(
                            scenario_name=scenario_name,
                            home_price=home_price,
                            down_payment_percent=dp_pct,
                            mortgage_rate=rate,
                            stock_price=stock_price,
                            sale_year=sale_year,
                            rsu_strategies=updated_strategies,
                            investments_to_liquidate=investments_to_liquidate,
                            use_cash=use_cash,
                            hoa_monthly=hoa_monthly
                        )

                        scenarios.append(result)

        # Generate recommendations
        recommendations = self._generate_recommendations(scenarios)

        return SimulationResult(
            config=self.config,
            scenarios=scenarios,
            rsu_sale_details=all_rsu_results,
            recommendations=recommendations
        )

    def _generate_recommendations(
        self,
        scenarios: list[ScenarioResult]
    ) -> list[str]:
        """Generate recommendations based on scenario results."""
        recommendations = []

        if not scenarios:
            return ["No scenarios to analyze."]

        # Find best scenarios by different criteria
        affordable_scenarios = [
            s for s in scenarios
            if s.affordability_metrics.passes_28_rule
            and s.affordability_metrics.passes_36_rule
        ]

        if not affordable_scenarios:
            recommendations.append(
                "WARNING: None of the scenarios pass the standard 28/36 "
                "affordability rules. Consider a lower home price or "
                "higher down payment."
            )
            affordable_scenarios = scenarios  # Continue analysis

        # Best by monthly payment
        best_monthly = min(affordable_scenarios, key=lambda s: s.monthly_payment)
        recommendations.append(
            f"Lowest monthly payment: {best_monthly.scenario_name} "
            f"at ${best_monthly.monthly_payment:,.0f}/month"
        )

        # Best by total upfront cost
        best_upfront = min(affordable_scenarios, key=lambda s: s.total_upfront_cost)
        recommendations.append(
            f"Lowest upfront cost: {best_upfront.scenario_name} "
            f"at ${best_upfront.total_upfront_cost:,.0f} total"
        )

        # Best by DTI
        best_dti = min(affordable_scenarios, key=lambda s: s.affordability_metrics.back_end_dti)
        recommendations.append(
            f"Best debt-to-income: {best_dti.scenario_name} "
            f"at {best_dti.affordability_metrics.back_end_dti*100:.1f}% DTI"
        )

        # 20% down payment analysis
        scenarios_20_down = [s for s in scenarios if s.down_payment_percent >= 0.20]
        scenarios_under_20 = [s for s in scenarios if s.down_payment_percent < 0.20]

        if scenarios_20_down and scenarios_under_20:
            avg_pmi_cost = sum(
                s.mortgage_summary.total_pmi_paid
                for s in scenarios_under_20
            ) / len(scenarios_under_20)

            if avg_pmi_cost > 5000:
                recommendations.append(
                    f"Consider 20% down payment to avoid ~${avg_pmi_cost:,.0f} "
                    "in PMI costs over the loan term."
                )

        # RSU timing recommendation
        for scenario in scenarios[:3]:  # Check first few
            if scenario.down_payment_plan.total_tax_impact > 20000:
                recommendations.append(
                    "High tax impact from RSU sales. Consider waiting for "
                    "long-term capital gains treatment (1+ year holding) "
                    "if timeline allows."
                )
                break

        return recommendations


def format_currency(amount: float) -> str:
    """Format a number as currency."""
    return f"${amount:,.2f}"


def format_percent(rate: float) -> str:
    """Format a decimal as percentage."""
    return f"{rate*100:.2f}%"


def print_scenario_summary(result: ScenarioResult) -> None:
    """Print a formatted summary of a scenario result."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {result.scenario_name}")
    print(f"{'='*60}")

    print(f"\nHome Price: {format_currency(result.home_price)}")
    print(f"Down Payment: {format_percent(result.down_payment_percent)} "
          f"({format_currency(result.home_price * result.down_payment_percent)})")
    print(f"Loan Amount: {format_currency(result.mortgage_summary.loan_amount)}")
    print(f"Mortgage Rate: {format_percent(result.mortgage_rate)}")

    print(f"\n--- Down Payment Funding ---")
    for source in result.down_payment_plan.sources:
        print(f"  {source.source_name}: {format_currency(source.amount)}")
        if source.tax_impact > 0:
            print(f"    Tax impact: -{format_currency(source.tax_impact)}")
            print(f"    Net: {format_currency(source.net_amount)}")

    print(f"\n--- Monthly Payment Breakdown ---")
    print(f"  Principal & Interest: {format_currency(result.mortgage_summary.monthly_pi)}")
    print(f"  Total PITI: {format_currency(result.mortgage_summary.monthly_piti)}")
    print(f"  Total Monthly: {format_currency(result.monthly_payment)}")
    print(f"  Effective (after tax benefit): {format_currency(result.effective_monthly_cost)}")

    print(f"\n--- Affordability Metrics ---")
    print(f"  Front-end DTI: {format_percent(result.affordability_metrics.front_end_dti)}"
          f" {'PASS' if result.affordability_metrics.passes_28_rule else 'FAIL'}")
    print(f"  Back-end DTI: {format_percent(result.affordability_metrics.back_end_dti)}"
          f" {'PASS' if result.affordability_metrics.passes_36_rule else 'FAIL'}")
    print(f"  Risk Level: {result.affordability_metrics.risk_level}")

    print(f"\n--- Upfront Costs ---")
    print(f"  Down Payment: {format_currency(result.down_payment_plan.total_needed)}")
    print(f"  Closing Costs: {format_currency(result.closing_costs.total_closing_costs)}")
    print(f"  Tax on Liquidations: {format_currency(result.first_year_tax_impact)}")
    print(f"  TOTAL UPFRONT: {format_currency(result.total_upfront_cost)}")

    print(f"\n--- Loan Summary ---")
    print(f"  Total Interest Paid: {format_currency(result.mortgage_summary.total_interest_paid)}")
    print(f"  Total PMI Paid: {format_currency(result.mortgage_summary.total_pmi_paid)}")
    print(f"  Total Cost of Loan: {format_currency(result.mortgage_summary.total_cost_of_loan)}")
