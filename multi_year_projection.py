"""
Multi-year projection module for home affordability analysis.

Provides detailed year-by-year and month-by-month projections of:
- Cash flow (income - expenses - housing costs)
- Net worth trajectory (home equity + liquid assets)
- Breakeven analysis (buying vs renting)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from config import (
    SimulationConfig,
    IncomeSchedule,
    FilingStatus,
    PropertyInputs,
    DebtItem
)
from tax_calculator import TaxCalculator, STANDARD_DEDUCTION_2024
from mortgage_calculator import MortgageCalculator


@dataclass
class MonthlySnapshot:
    """Detailed snapshot of finances for a single month."""
    year: int
    month: int  # 1-12

    # Income
    gross_monthly_income: float

    # Housing costs breakdown
    mortgage_principal: float
    mortgage_interest: float
    property_tax: float
    homeowners_insurance: float
    pmi: float
    hoa: float
    maintenance_reserve: float  # Recommended 1% of home value annually

    # Other expenses
    other_debt_payments: float
    estimated_income_tax: float
    estimated_living_expenses: float

    # Computed values
    @property
    def total_housing_cost(self) -> float:
        return (
            self.mortgage_principal
            + self.mortgage_interest
            + self.property_tax
            + self.homeowners_insurance
            + self.pmi
            + self.hoa
            + self.maintenance_reserve
        )

    @property
    def total_expenses(self) -> float:
        return (
            self.total_housing_cost
            + self.other_debt_payments
            + self.estimated_income_tax
            + self.estimated_living_expenses
        )

    @property
    def net_cash_flow(self) -> float:
        return self.gross_monthly_income - self.total_expenses

    @property
    def housing_to_income_ratio(self) -> float:
        if self.gross_monthly_income == 0:
            return 0
        return self.total_housing_cost / self.gross_monthly_income


@dataclass
class YearlySnapshot:
    """Aggregated snapshot for a full year."""
    year: int
    months: list[MonthlySnapshot]

    # Asset values at end of year
    home_value: float
    mortgage_balance: float
    liquid_savings: float  # Cash + investments

    # Renting alternative (for comparison)
    rent_scenario_savings: float  # What you'd have if renting

    @property
    def total_gross_income(self) -> float:
        return sum(m.gross_monthly_income for m in self.months)

    @property
    def total_housing_cost(self) -> float:
        return sum(m.total_housing_cost for m in self.months)

    @property
    def total_mortgage_interest(self) -> float:
        return sum(m.mortgage_interest for m in self.months)

    @property
    def total_mortgage_principal(self) -> float:
        return sum(m.mortgage_principal for m in self.months)

    @property
    def total_pmi(self) -> float:
        return sum(m.pmi for m in self.months)

    @property
    def total_net_cash_flow(self) -> float:
        return sum(m.net_cash_flow for m in self.months)

    @property
    def home_equity(self) -> float:
        return self.home_value - self.mortgage_balance

    @property
    def net_worth_buying(self) -> float:
        return self.home_equity + self.liquid_savings

    @property
    def net_worth_renting(self) -> float:
        return self.rent_scenario_savings

    @property
    def buying_advantage(self) -> float:
        """Positive means buying is ahead, negative means renting is ahead."""
        return self.net_worth_buying - self.net_worth_renting

    @property
    def average_monthly_cash_flow(self) -> float:
        if not self.months:
            return 0
        return self.total_net_cash_flow / len(self.months)


@dataclass
class BreakevenAnalysis:
    """Analysis of when buying becomes better than renting."""
    breakeven_month: Optional[int]  # Months from purchase, None if never
    breakeven_year: Optional[int]

    # At breakeven point
    home_equity_at_breakeven: Optional[float]
    total_housing_costs_to_breakeven: Optional[float]
    total_rent_to_breakeven: Optional[float]

    # If selling at different points
    selling_scenarios: list[dict]  # List of {year, net_proceeds, vs_renting}


@dataclass
class MultiYearProjection:
    """Complete multi-year projection results."""
    # Configuration
    home_price: float
    down_payment: float
    mortgage_rate: float
    projection_years: int

    # Yearly snapshots
    yearly_snapshots: list[YearlySnapshot]

    # Summary statistics
    total_housing_costs: float
    total_mortgage_interest_paid: float
    total_pmi_paid: float
    total_principal_paid: float
    final_home_equity: float
    final_net_worth: float

    # Breakeven analysis
    breakeven: BreakevenAnalysis

    # Cash flow warnings
    negative_cash_flow_months: list[tuple[int, int, float]]  # (year, month, amount)


class MultiYearProjector:
    """Generates multi-year financial projections for home purchase."""

    def __init__(
        self,
        config: SimulationConfig,
        property_inputs: PropertyInputs,
        initial_liquid_savings: float,
        upfront_costs_paid: float  # Down payment + closing + taxes on liquidations
    ):
        self.config = config
        self.property = property_inputs
        self.initial_liquid_savings = initial_liquid_savings
        self.upfront_costs_paid = upfront_costs_paid

        self.tax_calc = TaxCalculator(
            filing_status=config.filing_status,
            state=config.state
        )
        self.mortgage_calc = MortgageCalculator(property_inputs)

    def project(
        self,
        years: int = 10,
        start_year: int = None,
        monthly_living_expenses: float = 4000,
        annual_home_appreciation: float = 0.03,
        annual_rent_increase: float = 0.04,
        annual_property_tax_increase: float = 0.02,
        annual_insurance_increase: float = 0.03,
        comparable_monthly_rent: float = None,
        investment_return_rate: float = 0.07,
        include_maintenance: bool = True,
        maintenance_rate: float = 0.01  # 1% of home value annually
    ) -> MultiYearProjection:
        """
        Generate multi-year projection.

        Args:
            years: Number of years to project
            start_year: Starting year (default: current year)
            monthly_living_expenses: Non-housing living expenses
            annual_home_appreciation: Expected home value appreciation rate
            annual_rent_increase: Expected rent increase rate
            annual_property_tax_increase: Property tax increase rate
            annual_insurance_increase: Insurance cost increase rate
            comparable_monthly_rent: Rent for comparable property (for comparison)
            investment_return_rate: Return rate for investments
            include_maintenance: Whether to include maintenance reserve
            maintenance_rate: Annual maintenance as % of home value

        Returns:
            MultiYearProjection with all details
        """
        if start_year is None:
            start_year = date.today().year

        if comparable_monthly_rent is None:
            # Rough estimate: monthly rent ≈ 0.004-0.005 of home value
            comparable_monthly_rent = self.property.home_price * 0.004

        # Generate full amortization schedule
        amortization = self.mortgage_calc.generate_amortization_schedule(years * 12)

        # Track state over time
        yearly_snapshots = []
        cumulative_liquid_savings = self.initial_liquid_savings - self.upfront_costs_paid
        rent_scenario_savings = self.initial_liquid_savings  # Down payment invested instead

        current_home_value = self.property.home_price
        current_rent = comparable_monthly_rent
        current_property_tax_rate = self.property.property_tax_rate
        current_insurance = self.property.homeowners_insurance_annual

        negative_cash_flow_months = []

        total_housing_costs = 0
        total_interest_paid = 0
        total_pmi_paid = 0
        total_principal_paid = 0

        # Breakeven tracking
        breakeven_month = None
        breakeven_data = {}
        selling_scenarios = []

        for year_idx in range(years):
            year = start_year + year_idx
            monthly_snapshots = []

            # Get income for this year
            income_schedule = self.config.get_income_for_year(year)
            if income_schedule:
                annual_income = income_schedule.total_income
            elif self.config.income_schedule:
                # Use last known income with small increase
                last_income = self.config.income_schedule[-1].total_income
                years_beyond = year - self.config.income_schedule[-1].year
                annual_income = last_income * (1.02 ** years_beyond)
            else:
                annual_income = 200000  # Default fallback

            monthly_income = annual_income / 12

            # Calculate tax estimates for this year
            # Estimate mortgage interest for full year for tax calculation
            year_start_month = year_idx * 12
            year_end_month = min((year_idx + 1) * 12, len(amortization))
            year_interest = sum(
                amortization[m].interest
                for m in range(year_start_month, year_end_month)
            )

            # Estimate tax benefit from mortgage interest
            annual_property_tax = current_home_value * current_property_tax_rate
            salt_deduction = min(annual_property_tax, 10000)  # SALT cap
            potential_itemized = year_interest + salt_deduction
            standard_deduction = STANDARD_DEDUCTION_2024[self.config.filing_status]

            # Calculate effective tax rate
            effective_tax_rate = self._estimate_effective_tax_rate(annual_income)

            # Tax benefit from itemizing (if applicable)
            if potential_itemized > standard_deduction:
                annual_tax_benefit = (potential_itemized - standard_deduction) * effective_tax_rate
            else:
                annual_tax_benefit = 0

            monthly_tax_benefit = annual_tax_benefit / 12

            # Monthly maintenance reserve
            monthly_maintenance = (current_home_value * maintenance_rate / 12) if include_maintenance else 0

            # Other debt payments
            other_debt = sum(d.monthly_payment for d in self.config.existing_debts)

            # Process each month
            for month_in_year in range(12):
                month_idx = year_idx * 12 + month_in_year

                if month_idx >= len(amortization):
                    break

                amort_entry = amortization[month_idx]

                # Monthly housing costs
                monthly_property_tax = current_home_value * current_property_tax_rate / 12
                monthly_insurance = current_insurance / 12

                # Estimate income tax (simplified)
                monthly_income_tax = monthly_income * effective_tax_rate - monthly_tax_benefit

                snapshot = MonthlySnapshot(
                    year=year,
                    month=month_in_year + 1,
                    gross_monthly_income=monthly_income,
                    mortgage_principal=amort_entry.principal,
                    mortgage_interest=amort_entry.interest,
                    property_tax=monthly_property_tax,
                    homeowners_insurance=monthly_insurance,
                    pmi=amort_entry.pmi,
                    hoa=self.property.hoa_monthly,
                    maintenance_reserve=monthly_maintenance,
                    other_debt_payments=other_debt,
                    estimated_income_tax=monthly_income_tax,
                    estimated_living_expenses=monthly_living_expenses
                )

                monthly_snapshots.append(snapshot)

                # Track totals
                total_housing_costs += snapshot.total_housing_cost
                total_interest_paid += amort_entry.interest
                total_pmi_paid += amort_entry.pmi
                total_principal_paid += amort_entry.principal

                # Update cumulative savings
                cumulative_liquid_savings += snapshot.net_cash_flow

                # Track negative cash flow months
                if snapshot.net_cash_flow < 0:
                    negative_cash_flow_months.append(
                        (year, month_in_year + 1, snapshot.net_cash_flow)
                    )

                # Update rent scenario
                rent_monthly_cost = current_rent + monthly_living_expenses + other_debt
                rent_monthly_tax = monthly_income * effective_tax_rate  # No mortgage deduction
                rent_net_cash_flow = monthly_income - rent_monthly_cost - rent_monthly_tax

                # Rent savings grow with investment returns (monthly compounding)
                monthly_return = (1 + investment_return_rate) ** (1/12) - 1
                rent_scenario_savings = rent_scenario_savings * (1 + monthly_return) + rent_net_cash_flow

                # Check breakeven
                current_equity = current_home_value - amort_entry.remaining_balance
                current_net_worth_buying = current_equity + cumulative_liquid_savings

                if breakeven_month is None and current_net_worth_buying >= rent_scenario_savings:
                    breakeven_month = month_idx + 1
                    breakeven_data = {
                        'home_equity': current_equity,
                        'total_housing_costs': total_housing_costs,
                        'total_rent': current_rent * (month_idx + 1) * 0.5  # Rough average
                    }

            # End of year updates
            mortgage_balance = amortization[min(year_end_month - 1, len(amortization) - 1)].remaining_balance

            yearly_snapshot = YearlySnapshot(
                year=year,
                months=monthly_snapshots,
                home_value=current_home_value,
                mortgage_balance=mortgage_balance,
                liquid_savings=cumulative_liquid_savings,
                rent_scenario_savings=rent_scenario_savings
            )
            yearly_snapshots.append(yearly_snapshot)

            # Calculate selling scenario for this year
            selling_costs = current_home_value * 0.06  # 6% agent fees
            net_proceeds_if_sold = current_home_value - mortgage_balance - selling_costs
            total_if_sold = net_proceeds_if_sold + cumulative_liquid_savings

            selling_scenarios.append({
                'year': year,
                'years_owned': year_idx + 1,
                'home_value': current_home_value,
                'mortgage_balance': mortgage_balance,
                'selling_costs': selling_costs,
                'net_proceeds': net_proceeds_if_sold,
                'total_with_savings': total_if_sold,
                'rent_alternative': rent_scenario_savings,
                'vs_renting': total_if_sold - rent_scenario_savings
            })

            # Appreciate/inflate for next year
            current_home_value *= (1 + annual_home_appreciation)
            current_rent *= (1 + annual_rent_increase)
            current_property_tax_rate *= (1 + annual_property_tax_increase)
            current_insurance *= (1 + annual_insurance_increase)

        # Build breakeven analysis
        breakeven = BreakevenAnalysis(
            breakeven_month=breakeven_month,
            breakeven_year=start_year + (breakeven_month // 12) if breakeven_month else None,
            home_equity_at_breakeven=breakeven_data.get('home_equity'),
            total_housing_costs_to_breakeven=breakeven_data.get('total_housing_costs'),
            total_rent_to_breakeven=breakeven_data.get('total_rent'),
            selling_scenarios=selling_scenarios
        )

        # Final values
        final_snapshot = yearly_snapshots[-1] if yearly_snapshots else None

        return MultiYearProjection(
            home_price=self.property.home_price,
            down_payment=self.property.down_payment,
            mortgage_rate=self.property.mortgage_rate,
            projection_years=years,
            yearly_snapshots=yearly_snapshots,
            total_housing_costs=total_housing_costs,
            total_mortgage_interest_paid=total_interest_paid,
            total_pmi_paid=total_pmi_paid,
            total_principal_paid=total_principal_paid,
            final_home_equity=final_snapshot.home_equity if final_snapshot else 0,
            final_net_worth=final_snapshot.net_worth_buying if final_snapshot else 0,
            breakeven=breakeven,
            negative_cash_flow_months=negative_cash_flow_months
        )

    def _estimate_effective_tax_rate(self, annual_income: float) -> float:
        """Estimate combined federal + state effective tax rate."""
        # Simplified calculation
        federal_tax = self.tax_calc.calculate_federal_income_tax(annual_income)
        state_tax = self.tax_calc.calculate_california_income_tax(annual_income)
        ss_tax, medicare_tax = self.tax_calc.calculate_payroll_taxes(annual_income)

        total_tax = federal_tax + state_tax + ss_tax + medicare_tax
        return total_tax / annual_income if annual_income > 0 else 0.3


def print_projection_summary(projection: MultiYearProjection) -> None:
    """Print a formatted summary of the multi-year projection."""
    print("\n" + "=" * 70)
    print("MULTI-YEAR PROJECTION SUMMARY")
    print("=" * 70)

    print(f"\nHome Price: ${projection.home_price:,.0f}")
    print(f"Down Payment: ${projection.down_payment:,.0f}")
    print(f"Mortgage Rate: {projection.mortgage_rate * 100:.2f}%")
    print(f"Projection Period: {projection.projection_years} years")

    # Yearly summary table
    print("\n" + "-" * 70)
    print("YEAR-BY-YEAR SUMMARY")
    print("-" * 70)
    print(f"{'Year':<6} {'Income':>12} {'Housing':>12} {'Cash Flow':>12} {'Net Worth':>12} {'vs Rent':>12}")
    print("-" * 70)

    for snapshot in projection.yearly_snapshots:
        vs_rent = snapshot.buying_advantage
        vs_rent_str = f"+${vs_rent:,.0f}" if vs_rent >= 0 else f"-${abs(vs_rent):,.0f}"

        print(
            f"{snapshot.year:<6} "
            f"${snapshot.total_gross_income:>10,.0f} "
            f"${snapshot.total_housing_cost:>10,.0f} "
            f"${snapshot.total_net_cash_flow:>10,.0f} "
            f"${snapshot.net_worth_buying:>10,.0f} "
            f"{vs_rent_str:>12}"
        )

    # Cash flow analysis
    print("\n" + "-" * 70)
    print("CASH FLOW ANALYSIS")
    print("-" * 70)

    if projection.negative_cash_flow_months:
        print(f"\nWARNING: {len(projection.negative_cash_flow_months)} months with negative cash flow:")
        for year, month, amount in projection.negative_cash_flow_months[:5]:
            print(f"  {year}-{month:02d}: ${amount:,.0f}")
        if len(projection.negative_cash_flow_months) > 5:
            print(f"  ... and {len(projection.negative_cash_flow_months) - 5} more months")
    else:
        print("\nAll months have positive cash flow.")

    # Average monthly cash flow by year
    print("\nAverage Monthly Cash Flow by Year:")
    for snapshot in projection.yearly_snapshots:
        print(f"  {snapshot.year}: ${snapshot.average_monthly_cash_flow:,.0f}/month")

    # Breakeven analysis
    print("\n" + "-" * 70)
    print("BREAKEVEN ANALYSIS (Buying vs Renting)")
    print("-" * 70)

    if projection.breakeven.breakeven_month:
        years = projection.breakeven.breakeven_month // 12
        months = projection.breakeven.breakeven_month % 12
        print(f"\nBreakeven Point: {years} years, {months} months after purchase")
        print(f"  Home equity at breakeven: ${projection.breakeven.home_equity_at_breakeven:,.0f}")
    else:
        print(f"\nBreakeven not reached within {projection.projection_years} years")

    print("\nIf You Sell After Each Year:")
    print(f"{'Year':>6} {'Home Value':>14} {'Net Proceeds':>14} {'vs Renting':>14}")

    for scenario in projection.breakeven.selling_scenarios:
        vs_rent = scenario['vs_renting']
        vs_rent_str = f"+${vs_rent:,.0f}" if vs_rent >= 0 else f"-${abs(vs_rent):,.0f}"

        print(
            f"{scenario['years_owned']:>6} "
            f"${scenario['home_value']:>12,.0f} "
            f"${scenario['net_proceeds']:>12,.0f} "
            f"{vs_rent_str:>14}"
        )

    # Total costs
    print("\n" + "-" * 70)
    print("TOTAL COSTS OVER PROJECTION PERIOD")
    print("-" * 70)
    print(f"  Total Housing Costs: ${projection.total_housing_costs:,.0f}")
    print(f"  Total Interest Paid: ${projection.total_mortgage_interest_paid:,.0f}")
    print(f"  Total PMI Paid: ${projection.total_pmi_paid:,.0f}")
    print(f"  Total Principal Paid: ${projection.total_principal_paid:,.0f}")
    print(f"  Final Home Equity: ${projection.final_home_equity:,.0f}")
    print(f"  Final Net Worth: ${projection.final_net_worth:,.0f}")


def print_monthly_detail(projection: MultiYearProjection, year: int) -> None:
    """Print detailed monthly breakdown for a specific year."""
    snapshot = next((s for s in projection.yearly_snapshots if s.year == year), None)

    if not snapshot:
        print(f"No data for year {year}")
        return

    print(f"\n{'=' * 80}")
    print(f"MONTHLY DETAIL FOR {year}")
    print(f"{'=' * 80}")

    print(f"\n{'Month':<6} {'Income':>10} {'P&I':>10} {'Tax+Ins':>10} {'PMI':>8} "
          f"{'HOA':>8} {'Other':>10} {'Net Flow':>10}")
    print("-" * 80)

    for m in snapshot.months:
        pi = m.mortgage_principal + m.mortgage_interest
        tax_ins = m.property_tax + m.homeowners_insurance
        other = m.other_debt_payments + m.estimated_income_tax + m.estimated_living_expenses

        print(
            f"{m.month:<6} "
            f"${m.gross_monthly_income:>8,.0f} "
            f"${pi:>8,.0f} "
            f"${tax_ins:>8,.0f} "
            f"${m.pmi:>6,.0f} "
            f"${m.hoa:>6,.0f} "
            f"${other:>8,.0f} "
            f"${m.net_cash_flow:>8,.0f}"
        )

    print("-" * 80)
    print(f"{'TOTAL':<6} "
          f"${snapshot.total_gross_income:>8,.0f} "
          f"${snapshot.total_mortgage_principal + snapshot.total_mortgage_interest:>8,.0f} "
          f"${sum(m.property_tax + m.homeowners_insurance for m in snapshot.months):>8,.0f} "
          f"${snapshot.total_pmi:>6,.0f} "
          f"${sum(m.hoa for m in snapshot.months):>6,.0f} "
          f"${sum(m.other_debt_payments + m.estimated_income_tax + m.estimated_living_expenses for m in snapshot.months):>8,.0f} "
          f"${snapshot.total_net_cash_flow:>8,.0f}")


def generate_csv_export(projection: MultiYearProjection, filename: str) -> None:
    """Export projection to CSV for further analysis."""
    import csv

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Year', 'Month', 'Gross Income', 'Principal', 'Interest',
            'Property Tax', 'Insurance', 'PMI', 'HOA', 'Maintenance',
            'Other Debt', 'Income Tax', 'Living Expenses',
            'Total Housing', 'Net Cash Flow', 'Housing/Income Ratio'
        ])

        # Data rows
        for yearly in projection.yearly_snapshots:
            for m in yearly.months:
                writer.writerow([
                    m.year, m.month, m.gross_monthly_income,
                    m.mortgage_principal, m.mortgage_interest,
                    m.property_tax, m.homeowners_insurance, m.pmi,
                    m.hoa, m.maintenance_reserve,
                    m.other_debt_payments, m.estimated_income_tax,
                    m.estimated_living_expenses,
                    m.total_housing_cost, m.net_cash_flow,
                    f"{m.housing_to_income_ratio:.2%}"
                ])

    print(f"Exported to {filename}")
