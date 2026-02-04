"""
Unified Financial Simulation Engine.

This is the core simulation engine that processes all financial decisions
month-by-month, tracking cash flow, net worth, and providing comprehensive
analysis.

The simulation integrates:
- Income (with annual changes)
- RSU vesting and selling strategies
- Investment growth and liquidation
- Home purchase decisions
- Tax calculations
- Cash flow tracking
"""

from dataclasses import dataclass, field
from datetime import date
from dateutil.relativedelta import relativedelta
from enum import Enum
from typing import Optional
from copy import deepcopy

from config import FilingStatus, InvestmentType, RSUTerm
from tax_calculator import TaxCalculator


# =============================================================================
# CONSTANTS
# =============================================================================

# RSU vest withholding rate (sell-to-cover)
# California: ~37% (22% federal supplemental + 10.23% CA + 1.45% Medicare + ~3% SS)
# This percentage of shares is sold at vesting to cover taxes
RSU_VEST_WITHHOLDING_RATE = 0.37

# Default closing costs as percentage of home price
CLOSING_COST_RATE = 0.03


# =============================================================================
# INPUT DATA STRUCTURES
# =============================================================================

@dataclass
class RSULot:
    """A single RSU lot (vested shares)."""
    lot_id: str
    shares: int
    cost_basis_per_share: float  # Price at vesting (taxed as income)
    vest_date: date

    def get_term(self, sale_date: date) -> RSUTerm:
        """Determine if short-term or long-term based on holding period."""
        days_held = (sale_date - self.vest_date).days
        return RSUTerm.LONG_TERM if days_held >= 365 else RSUTerm.SHORT_TERM

    @property
    def cost_basis_total(self) -> float:
        return self.shares * self.cost_basis_per_share


@dataclass
class FutureRSUVest:
    """A future RSU vesting event."""
    vest_id: str
    shares: int
    vest_date: date
    grant_date: Optional[date] = None


@dataclass
class IncomeProfile:
    """Annual income profile."""
    year: int
    base_salary: float
    bonus: float = 0.0
    other_income: float = 0.0

    @property
    def total_annual(self) -> float:
        return self.base_salary + self.bonus + self.other_income

    @property
    def monthly_salary(self) -> float:
        return self.base_salary / 12


@dataclass
class InvestmentAccount:
    """An investment account."""
    name: str
    account_type: InvestmentType
    balance: float
    cost_basis: float
    annual_return: float = 0.05
    is_liquid: bool = True

    @property
    def unrealized_gain(self) -> float:
        return self.balance - self.cost_basis


@dataclass
class DebtObligation:
    """An existing debt."""
    name: str
    monthly_payment: float
    remaining_balance: float = 0.0
    interest_rate: float = 0.0


@dataclass
class HousePurchasePlan:
    """Plan for purchasing a house."""
    purchase_date: date
    home_price: float
    down_payment_percent: float
    mortgage_rate: float
    loan_term_years: int = 30
    property_tax_rate: float = 0.0125
    hoa_monthly: float = 0.0
    homeowners_insurance_annual: float = 2000.0
    maintenance_rate: float = 0.01  # Annual maintenance as % of home value

    def __post_init__(self):
        """Validate house purchase plan inputs."""
        if self.home_price <= 0:
            raise ValueError("home_price must be positive")
        if not 0 <= self.down_payment_percent <= 1:
            raise ValueError("down_payment_percent must be between 0 and 1")
        if self.mortgage_rate < 0 or self.mortgage_rate > 0.25:
            raise ValueError("mortgage_rate must be between 0 and 0.25 (25%)")
        if self.loan_term_years <= 0 or self.loan_term_years > 50:
            raise ValueError("loan_term_years must be between 1 and 50")
        if self.property_tax_rate < 0:
            raise ValueError("property_tax_rate cannot be negative")
        if self.hoa_monthly < 0:
            raise ValueError("hoa_monthly cannot be negative")

    @property
    def down_payment(self) -> float:
        return self.home_price * self.down_payment_percent

    @property
    def loan_amount(self) -> float:
        return self.home_price - self.down_payment

    @property
    def requires_pmi(self) -> bool:
        return self.down_payment_percent < 0.20


class RSUSellStrategy(Enum):
    """Strategy for selling RSUs."""
    SELL_IMMEDIATELY = "sell_immediately"  # Sell as soon as they vest
    SELL_AT_PURCHASE = "sell_at_purchase"  # Sell to fund home purchase
    SELL_LONG_TERM = "sell_long_term"  # Wait for long-term treatment
    HOLD = "hold"  # Don't sell
    CUSTOM = "custom"  # Use custom sell schedule


@dataclass
class RSUSellRule:
    """Rule for when to sell specific RSU lots."""
    lot_id: str  # "all" for all lots
    sell_date: Optional[date] = None  # Specific date to sell
    strategy: RSUSellStrategy = RSUSellStrategy.HOLD
    shares_to_sell: Optional[int] = None  # None = all shares


@dataclass
class MarketAssumptions:
    """Market and economic assumptions."""
    stock_prices: dict[date, float] = field(default_factory=dict)  # Date -> price
    current_stock_price: float = 100.0
    stock_annual_growth: float = 0.08  # If no specific prices given
    home_appreciation_rate: float = 0.03
    rent_increase_rate: float = 0.04
    inflation_rate: float = 0.03
    investment_return_rate: float = 0.07

    def get_stock_price(self, target_date: date) -> float:
        """Get stock price for a given date."""
        # Check for exact or nearby date
        if target_date in self.stock_prices:
            return self.stock_prices[target_date]

        # Find closest earlier date
        earlier_dates = [d for d in self.stock_prices if d <= target_date]
        if earlier_dates:
            closest = max(earlier_dates)
            base_price = self.stock_prices[closest]
            # Grow from that date
            days = (target_date - closest).days
            return base_price * ((1 + self.stock_annual_growth) ** (days / 365))

        # No earlier dates, use current price and grow
        if self.stock_prices:
            earliest = min(self.stock_prices.keys())
            if target_date < earliest:
                return self.current_stock_price

        # Default: grow from current price
        return self.current_stock_price


@dataclass
class SimulationInputs:
    """All inputs for the simulation."""
    # Personal info
    filing_status: FilingStatus
    state: str = "CA"

    # Starting state
    start_date: date = field(default_factory=lambda: date.today().replace(day=1))
    initial_cash: float = 0.0

    # Income
    income_schedule: list[IncomeProfile] = field(default_factory=list)

    # RSUs
    rsu_holdings: list[RSULot] = field(default_factory=list)
    future_rsu_vests: list[FutureRSUVest] = field(default_factory=list)
    rsu_sell_rules: list[RSUSellRule] = field(default_factory=list)
    stock_symbol: str = "STOCK"

    # Other investments
    investments: list[InvestmentAccount] = field(default_factory=list)

    # Debts
    debts: list[DebtObligation] = field(default_factory=list)

    # House purchase
    house_plan: Optional[HousePurchasePlan] = None
    comparable_rent: float = 3000.0  # Monthly rent if not buying

    # Expenses
    monthly_living_expenses: float = 4000.0

    # Market assumptions
    market: MarketAssumptions = field(default_factory=MarketAssumptions)

    # Simulation period
    simulation_years: int = 10

    def __post_init__(self):
        """Validate simulation inputs."""
        if self.initial_cash < 0:
            raise ValueError("initial_cash cannot be negative")
        if self.comparable_rent < 0:
            raise ValueError("comparable_rent cannot be negative")
        if self.monthly_living_expenses < 0:
            raise ValueError("monthly_living_expenses cannot be negative")
        if self.simulation_years <= 0 or self.simulation_years > 50:
            raise ValueError("simulation_years must be between 1 and 50")
        # Validate income schedules have positive values
        for income in self.income_schedule:
            if income.base_salary < 0:
                raise ValueError(f"base_salary for year {income.year} cannot be negative")

    def get_income_for_year(self, year: int) -> Optional[IncomeProfile]:
        """Get income profile for a specific year."""
        for inc in self.income_schedule:
            if inc.year == year:
                return inc
        return None

    def get_rsu_lots_available(self, as_of: date) -> list[RSULot]:
        """Get RSU lots available for sale as of a given date."""
        return [lot for lot in self.rsu_holdings if lot.vest_date <= as_of and lot.shares > 0]


# =============================================================================
# STATE TRACKING
# =============================================================================

@dataclass
class MortgageState:
    """Current state of a mortgage."""
    original_principal: float
    remaining_balance: float
    monthly_payment: float  # P&I only
    interest_rate: float
    start_date: date
    term_months: int

    def calculate_month_payment(self) -> tuple[float, float]:
        """Calculate principal and interest for current month."""
        monthly_rate = self.interest_rate / 12
        interest = self.remaining_balance * monthly_rate
        principal = self.monthly_payment - interest
        return principal, interest


@dataclass
class HomeState:
    """Current state of home ownership."""
    purchase_date: date
    purchase_price: float
    current_value: float
    mortgage: MortgageState
    property_tax_rate: float
    hoa_monthly: float
    insurance_annual: float
    maintenance_rate: float
    pmi_rate: float = 0.005

    @property
    def equity(self) -> float:
        return self.current_value - self.mortgage.remaining_balance

    @property
    def ltv(self) -> float:
        return self.mortgage.remaining_balance / self.current_value

    @property
    def requires_pmi(self) -> bool:
        return self.ltv > 0.80


@dataclass
class MonthlySnapshot:
    """Complete financial snapshot for a month."""
    date: date
    year: int
    month: int

    # Income
    gross_income: float
    rsu_vest_income: float  # Value of RSUs vested this month (taxed as income)
    rsu_sale_proceeds: float  # Gross proceeds from RSU sales
    rsu_sale_gains: float  # Capital gains from RSU sales

    # Assets at end of month
    cash_balance: float
    investment_balance: float
    rsu_holdings_value: float
    home_equity: float

    # Housing costs (if owning)
    mortgage_principal: float
    mortgage_interest: float
    property_tax: float
    homeowners_insurance: float
    pmi: float
    hoa: float
    maintenance: float

    # Housing costs (if renting)
    rent: float

    # Other expenses
    other_debt_payments: float
    income_tax_withheld: float
    living_expenses: float

    # Taxes paid this month (from RSU sales, etc.)
    capital_gains_tax_paid: float

    @property
    def total_housing_cost(self) -> float:
        """True housing cost (excludes principal which builds equity)."""
        if self.rent > 0:
            return self.rent
        return (
            self.mortgage_interest +
            self.property_tax + self.homeowners_insurance +
            self.pmi + self.hoa + self.maintenance
        )

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

    @property
    def total_expenses(self) -> float:
        """Total cash outflows (includes principal since it reduces cash)."""
        return (
            self.total_housing_cost +
            self.mortgage_principal +  # Principal is cash outflow even though it builds equity
            self.other_debt_payments +
            self.income_tax_withheld +
            self.living_expenses +
            self.capital_gains_tax_paid
        )

    @property
    def total_income(self) -> float:
        return self.gross_income + self.rsu_sale_proceeds

    @property
    def net_cash_flow(self) -> float:
        return self.total_income - self.total_expenses

    @property
    def net_worth(self) -> float:
        return (
            self.cash_balance +
            self.investment_balance +
            self.rsu_holdings_value +
            self.home_equity
        )

    @property
    def is_owning(self) -> bool:
        return self.rent == 0


@dataclass
class YearlySummary:
    """Aggregated summary for a year."""
    year: int
    months: list[MonthlySnapshot]

    @property
    def total_income(self) -> float:
        return sum(m.gross_income for m in self.months)

    @property
    def total_rsu_income(self) -> float:
        return sum(m.rsu_vest_income for m in self.months)

    @property
    def total_rsu_sale_proceeds(self) -> float:
        return sum(m.rsu_sale_proceeds for m in self.months)

    @property
    def total_housing_cost(self) -> float:
        return sum(m.total_housing_cost for m in self.months)

    @property
    def total_mortgage_interest(self) -> float:
        return sum(m.mortgage_interest for m in self.months)

    @property
    def total_net_cash_flow(self) -> float:
        return sum(m.net_cash_flow for m in self.months)

    @property
    def end_of_year_net_worth(self) -> float:
        return self.months[-1].net_worth if self.months else 0

    @property
    def average_monthly_cash_flow(self) -> float:
        return self.total_net_cash_flow / len(self.months) if self.months else 0


@dataclass
class SimulationResult:
    """Complete simulation results."""
    inputs: SimulationInputs
    monthly_snapshots: list[MonthlySnapshot]
    yearly_summaries: list[YearlySummary]

    # Comparison scenario (renting instead of buying)
    rent_scenario_snapshots: list[MonthlySnapshot]

    # Key events
    home_purchase_month: Optional[int] = None  # Month index when home was purchased
    pmi_removal_month: Optional[int] = None  # Month index when PMI was removed
    breakeven_month: Optional[int] = None  # Month when buying beats renting

    # Summary metrics
    total_housing_costs: float = 0
    total_mortgage_interest: float = 0
    total_pmi_paid: float = 0
    total_rsu_taxes_paid: float = 0

    @property
    def final_net_worth(self) -> float:
        return self.monthly_snapshots[-1].net_worth if self.monthly_snapshots else 0

    @property
    def rent_scenario_final_net_worth(self) -> float:
        return self.rent_scenario_snapshots[-1].net_worth if self.rent_scenario_snapshots else 0


# =============================================================================
# SIMULATION ENGINE
# =============================================================================

class FinancialSimulator:
    """
    Core simulation engine that processes all financial decisions month-by-month.
    """

    def __init__(self, inputs: SimulationInputs):
        self.inputs = inputs
        self.tax_calc = TaxCalculator(
            filing_status=inputs.filing_status,
            state=inputs.state
        )

        # Working state (mutated during simulation)
        self._cash = inputs.initial_cash
        self._investments = deepcopy(inputs.investments)
        self._rsu_holdings = deepcopy(inputs.rsu_holdings)
        self._debts = deepcopy(inputs.debts)
        self._home: Optional[HomeState] = None

        # Track for tax calculations
        self._ytd_income = 0.0

    def run(self) -> SimulationResult:
        """Run the complete simulation."""
        monthly_snapshots = []
        rent_scenario_snapshots = []

        # Initialize rent scenario state
        rent_cash = self.inputs.initial_cash
        rent_investments = deepcopy(self.inputs.investments)
        rent_rsu_holdings = deepcopy(self.inputs.rsu_holdings)
        rent_debts = deepcopy(self.inputs.debts)
        rent_ytd_income = 0.0

        start_date = self.inputs.start_date
        end_date = start_date + relativedelta(years=self.inputs.simulation_years)

        current_date = start_date
        month_index = 0

        home_purchase_month = None
        pmi_removal_month = None
        breakeven_month = None

        total_housing = 0
        total_interest = 0
        total_pmi = 0
        total_rsu_taxes = 0

        current_rent = self.inputs.comparable_rent

        while current_date < end_date:
            year = current_date.year
            month = current_date.month

            # Reset YTD trackers at start of year
            if month == 1:
                self._ytd_income = 0.0
                rent_ytd_income = 0.0

            # Get income for this year
            income_profile = self.inputs.get_income_for_year(year)
            if not income_profile:
                # Extrapolate from last known year
                income_profile = self._extrapolate_income(year)

            monthly_salary = income_profile.monthly_salary
            # Add bonus in December (or spread it - here we add in December)
            bonus_this_month = income_profile.bonus if month == 12 else 0

            gross_income = monthly_salary + bonus_this_month
            self._ytd_income += gross_income

            # Process RSU vests
            vest_income = self._process_rsu_vests(current_date)
            self._ytd_income += vest_income

            # Process RSU sales
            sale_proceeds, sale_gains, sale_taxes = self._process_rsu_sales(current_date)
            total_rsu_taxes += sale_taxes

            # Track liquidation taxes for this month
            liquidation_taxes = 0.0

            # Process home purchase if this is the month
            if (self.inputs.house_plan and
                self.inputs.house_plan.purchase_date.year == year and
                self.inputs.house_plan.purchase_date.month == month and
                self._home is None):
                liquidation_taxes = self._execute_home_purchase()
                home_purchase_month = month_index

            # Calculate housing costs
            housing_costs = self._calculate_housing_costs(current_date)

            # Update home value and mortgage if owning
            if self._home:
                # Appreciate home monthly
                monthly_appreciation = (1 + self.inputs.market.home_appreciation_rate) ** (1/12) - 1
                self._home.current_value *= (1 + monthly_appreciation)

                # Pay down mortgage
                if housing_costs.get('principal', 0) > 0:
                    self._home.mortgage.remaining_balance -= housing_costs['principal']

                # Check PMI removal
                if pmi_removal_month is None and not self._home.requires_pmi:
                    pmi_removal_month = month_index

            total_housing += sum(v for k, v in housing_costs.items() if k != 'principal')
            total_interest += housing_costs.get('interest', 0)
            total_pmi += housing_costs.get('pmi', 0)

            # Apply investment growth
            self._grow_investments()

            # Calculate and apply debt payments
            other_debt_payments = 0.0
            for debt in self._debts:
                if debt.remaining_balance > 0:
                    # Calculate interest portion
                    monthly_interest = debt.remaining_balance * (debt.interest_rate / 12)
                    principal_payment = debt.monthly_payment - monthly_interest

                    # Don't pay more than remaining balance
                    if principal_payment > debt.remaining_balance:
                        principal_payment = debt.remaining_balance
                        actual_payment = principal_payment + monthly_interest
                    else:
                        actual_payment = debt.monthly_payment

                    debt.remaining_balance -= principal_payment
                    other_debt_payments += actual_payment
                elif debt.remaining_balance == 0 and debt.interest_rate == 0:
                    # Simple recurring payment with no balance tracking (e.g., subscriptions)
                    other_debt_payments += debt.monthly_payment

            # Estimate income tax (simplified monthly withholding)
            tax_rate = self._estimate_tax_rate(income_profile.total_annual)
            income_tax = gross_income * tax_rate

            # Note: RSU vest withholding is handled via sell-to-cover in _process_rsu_vests
            # (shares are reduced, not cash deducted)

            # Apply all cash flows
            self._cash += gross_income + sale_proceeds
            self._cash -= sum(housing_costs.values())
            self._cash -= other_debt_payments
            self._cash -= income_tax
            self._cash -= self.inputs.monthly_living_expenses
            self._cash -= sale_taxes

            # Get RSU holdings value
            stock_price = self.inputs.market.get_stock_price(current_date)
            rsu_value = sum(lot.shares * stock_price for lot in self._rsu_holdings)

            # Create snapshot
            snapshot = MonthlySnapshot(
                date=current_date,
                year=year,
                month=month,
                gross_income=gross_income,
                rsu_vest_income=vest_income,
                rsu_sale_proceeds=sale_proceeds,
                rsu_sale_gains=sale_gains,
                cash_balance=self._cash,
                investment_balance=sum(inv.balance for inv in self._investments),
                rsu_holdings_value=rsu_value,
                home_equity=self._home.equity if self._home else 0,
                mortgage_principal=housing_costs.get('principal', 0),
                mortgage_interest=housing_costs.get('interest', 0),
                property_tax=housing_costs.get('property_tax', 0),
                homeowners_insurance=housing_costs.get('insurance', 0),
                pmi=housing_costs.get('pmi', 0),
                hoa=housing_costs.get('hoa', 0),
                maintenance=housing_costs.get('maintenance', 0),
                rent=housing_costs.get('rent', 0),
                other_debt_payments=other_debt_payments,
                income_tax_withheld=income_tax,
                living_expenses=self.inputs.monthly_living_expenses,
                capital_gains_tax_paid=sale_taxes + liquidation_taxes
            )
            monthly_snapshots.append(snapshot)

            # === RENT SCENARIO (parallel simulation) ===
            rent_snapshot, rent_ytd_income = self._simulate_rent_month(
                current_date, year, month, income_profile,
                rent_cash, rent_investments, rent_rsu_holdings, rent_debts,
                current_rent, stock_price, rent_ytd_income
            )
            rent_scenario_snapshots.append(rent_snapshot)

            # Update rent scenario state
            rent_cash = rent_snapshot.cash_balance

            # Check breakeven
            if breakeven_month is None and snapshot.net_worth > rent_snapshot.net_worth:
                breakeven_month = month_index

            # Advance to next month
            current_date += relativedelta(months=1)
            month_index += 1

            # Annual rent increase
            if month == 12:
                current_rent *= (1 + self.inputs.market.rent_increase_rate)

        # Build yearly summaries
        yearly_summaries = self._build_yearly_summaries(monthly_snapshots)

        return SimulationResult(
            inputs=self.inputs,
            monthly_snapshots=monthly_snapshots,
            yearly_summaries=yearly_summaries,
            rent_scenario_snapshots=rent_scenario_snapshots,
            home_purchase_month=home_purchase_month,
            pmi_removal_month=pmi_removal_month,
            breakeven_month=breakeven_month,
            total_housing_costs=total_housing,
            total_mortgage_interest=total_interest,
            total_pmi_paid=total_pmi,
            total_rsu_taxes_paid=total_rsu_taxes
        )

    def _extrapolate_income(self, year: int) -> IncomeProfile:
        """Extrapolate income for a year not in the schedule."""
        if not self.inputs.income_schedule:
            return IncomeProfile(year=year, base_salary=150000)

        last = max(self.inputs.income_schedule, key=lambda x: x.year)
        years_beyond = year - last.year
        growth = 1.03 ** years_beyond  # 3% annual growth

        return IncomeProfile(
            year=year,
            base_salary=last.base_salary * growth,
            bonus=last.bonus * growth
        )

    def _process_rsu_vests(self, current_date: date) -> float:
        """
        Process RSU vests for this month using sell-to-cover.

        In sell-to-cover, a portion of shares is automatically sold at vesting
        to cover tax withholding. Only the remaining shares are added to holdings.

        Returns:
            vest_income: Total value of vested shares (for tax tracking)
        """
        vest_income = 0.0
        stock_price = self.inputs.market.get_stock_price(current_date)

        # Check for scheduled vests
        for vest in self.inputs.future_rsu_vests:
            if (vest.vest_date.year == current_date.year and
                vest.vest_date.month == current_date.month):
                # Full vest value is taxable as ordinary income
                vest_income += vest.shares * stock_price

                # Sell-to-cover: only keep shares after withholding
                # (Company sells ~37% of shares to cover taxes)
                shares_after_withholding = int(vest.shares * (1 - RSU_VEST_WITHHOLDING_RATE))

                # Create lot with reduced share count
                if shares_after_withholding > 0:
                    new_lot = RSULot(
                        lot_id=vest.vest_id,
                        shares=shares_after_withholding,
                        cost_basis_per_share=stock_price,
                        vest_date=vest.vest_date
                    )
                    self._rsu_holdings.append(new_lot)

        return vest_income

    def _process_rsu_sales(self, current_date: date) -> tuple[float, float, float]:
        """Process RSU sales based on sell rules."""
        total_proceeds = 0.0
        total_gains = 0.0
        total_taxes = 0.0

        stock_price = self.inputs.market.get_stock_price(current_date)

        for rule in self.inputs.rsu_sell_rules:
            lots_to_process = []

            if rule.lot_id == "all":
                lots_to_process = [lot for lot in self._rsu_holdings if lot.shares > 0]
            else:
                lots_to_process = [lot for lot in self._rsu_holdings
                                   if lot.lot_id == rule.lot_id and lot.shares > 0]

            for lot in lots_to_process:
                should_sell = False

                if rule.strategy == RSUSellStrategy.SELL_IMMEDIATELY:
                    # Sell in the same month as vesting
                    if (lot.vest_date.year == current_date.year and
                        lot.vest_date.month == current_date.month):
                        should_sell = True

                elif rule.strategy == RSUSellStrategy.SELL_AT_PURCHASE:
                    # Sell in the month of home purchase
                    if self.inputs.house_plan:
                        hp = self.inputs.house_plan
                        if (hp.purchase_date.year == current_date.year and
                            hp.purchase_date.month == current_date.month):
                            should_sell = True

                elif rule.strategy == RSUSellStrategy.SELL_LONG_TERM:
                    # Sell when it becomes long-term
                    lt_date = lot.vest_date + relativedelta(years=1)
                    if (lt_date.year == current_date.year and
                        lt_date.month == current_date.month):
                        should_sell = True

                elif rule.strategy == RSUSellStrategy.CUSTOM and rule.sell_date:
                    if (rule.sell_date.year == current_date.year and
                        rule.sell_date.month == current_date.month):
                        should_sell = True

                if should_sell:
                    shares_to_sell = rule.shares_to_sell or lot.shares
                    shares_to_sell = min(shares_to_sell, lot.shares)

                    if shares_to_sell > 0:
                        proceeds = shares_to_sell * stock_price
                        cost_basis = shares_to_sell * lot.cost_basis_per_share
                        gain = proceeds - cost_basis

                        # Calculate taxes
                        term = lot.get_term(current_date)
                        tax = self._calculate_rsu_sale_tax(
                            gain, term, self._ytd_income
                        )

                        total_proceeds += proceeds
                        total_gains += gain
                        total_taxes += tax

                        # Update lot
                        lot.shares -= shares_to_sell

        return total_proceeds, total_gains, total_taxes

    def _calculate_rsu_sale_tax(
        self,
        gain: float,
        term: RSUTerm,
        ytd_income: float
    ) -> float:
        """Calculate tax on RSU sale."""
        if gain <= 0:
            return 0.0

        # Federal tax
        if term == RSUTerm.SHORT_TERM:
            stcg, _ = self.tax_calc.calculate_federal_capital_gains_tax(
                ytd_income, gain, 0
            )
            federal = stcg
        else:
            _, ltcg = self.tax_calc.calculate_federal_capital_gains_tax(
                ytd_income, 0, gain
            )
            federal = ltcg

        # NIIT
        niit = self.tax_calc.calculate_niit(ytd_income, gain)

        # California taxes all gains as ordinary income
        state = self._calculate_marginal_ca_tax(gain, ytd_income)

        return federal + niit + state

    def _calculate_marginal_ca_tax(self, gain: float, ytd_income: float) -> float:
        """Calculate marginal California tax on gain."""
        base = self.tax_calc.calculate_california_income_tax(ytd_income)
        with_gain = self.tax_calc.calculate_california_income_tax(ytd_income + gain)
        return with_gain - base

    def _execute_home_purchase(self) -> float:
        """Execute home purchase, updating state. Returns capital gains taxes paid."""
        plan = self.inputs.house_plan

        # Calculate closing costs (typically 2-5% of home price)
        closing_costs = plan.home_price * CLOSING_COST_RATE

        # Total cash needed
        total_upfront = plan.down_payment + closing_costs

        # First, use cash
        cash_used = min(self._cash, total_upfront)
        self._cash -= cash_used
        remaining = total_upfront - cash_used

        # Track capital gains taxes from liquidation
        liquidation_taxes = 0.0

        # If not enough cash, liquidate investments (lowest gains first to minimize taxes)
        if remaining > 0:
            for inv in sorted(self._investments, key=lambda x: x.unrealized_gain):
                if remaining <= 0:
                    break

                liquidate = min(inv.balance, remaining)

                # Calculate proportional gains and taxes
                if inv.balance > 0 and liquidate > 0:
                    proportion = liquidate / inv.balance
                    gain = inv.unrealized_gain * proportion

                    if gain > 0:
                        # Calculate capital gains tax (assume long-term for investments)
                        _, ltcg_tax = self.tax_calc.calculate_federal_capital_gains_tax(
                            self._ytd_income, 0, gain
                        )
                        niit = self.tax_calc.calculate_niit(self._ytd_income, gain)
                        state_tax = self._calculate_marginal_ca_tax(gain, self._ytd_income)
                        liquidation_taxes += ltcg_tax + niit + state_tax

                    # Update cost basis proportionally
                    inv.cost_basis -= inv.cost_basis * proportion

                inv.balance -= liquidate
                remaining -= liquidate

        # Deduct liquidation taxes from cash
        self._cash -= liquidation_taxes

        # Create mortgage
        monthly_payment = self._calculate_monthly_pi(
            plan.loan_amount, plan.mortgage_rate, plan.loan_term_years
        )

        mortgage = MortgageState(
            original_principal=plan.loan_amount,
            remaining_balance=plan.loan_amount,
            monthly_payment=monthly_payment,
            interest_rate=plan.mortgage_rate,
            start_date=plan.purchase_date,
            term_months=plan.loan_term_years * 12
        )

        self._home = HomeState(
            purchase_date=plan.purchase_date,
            purchase_price=plan.home_price,
            current_value=plan.home_price,
            mortgage=mortgage,
            property_tax_rate=plan.property_tax_rate,
            hoa_monthly=plan.hoa_monthly,
            insurance_annual=plan.homeowners_insurance_annual,
            maintenance_rate=plan.maintenance_rate
        )

        return liquidation_taxes

    def _calculate_monthly_pi(
        self,
        principal: float,
        annual_rate: float,
        term_years: int
    ) -> float:
        """Calculate monthly principal and interest payment."""
        if annual_rate == 0:
            return principal / (term_years * 12)

        monthly_rate = annual_rate / 12
        num_payments = term_years * 12

        return principal * (
            (monthly_rate * (1 + monthly_rate) ** num_payments) /
            ((1 + monthly_rate) ** num_payments - 1)
        )

    def _calculate_housing_costs(self, current_date: date) -> dict:
        """Calculate all housing costs for the month."""
        if self._home is None:
            return {'rent': self.inputs.comparable_rent}

        home = self._home
        principal, interest = home.mortgage.calculate_month_payment()

        costs = {
            'principal': principal,
            'interest': interest,
            'property_tax': home.current_value * home.property_tax_rate / 12,
            'insurance': home.insurance_annual / 12,
            'hoa': home.hoa_monthly,
            'maintenance': home.current_value * home.maintenance_rate / 12,
            'pmi': 0.0
        }

        if home.requires_pmi:
            costs['pmi'] = home.mortgage.remaining_balance * home.pmi_rate / 12

        return costs

    def _grow_investments(self):
        """Apply monthly investment growth."""
        for inv in self._investments:
            monthly_return = (1 + inv.annual_return) ** (1/12) - 1
            inv.balance *= (1 + monthly_return)

    def _estimate_tax_rate(self, annual_income: float) -> float:
        """Estimate effective monthly tax withholding rate."""
        federal = self.tax_calc.calculate_federal_income_tax(annual_income)
        state = self.tax_calc.calculate_california_income_tax(annual_income)
        fica_ss, fica_med = self.tax_calc.calculate_payroll_taxes(annual_income)

        total = federal + state + fica_ss + fica_med
        return total / annual_income if annual_income > 0 else 0.3

    def _simulate_rent_month(
        self,
        current_date: date,
        year: int,
        month: int,
        income_profile: IncomeProfile,
        cash: float,
        investments: list[InvestmentAccount],
        rsu_holdings: list[RSULot],
        debts: list[DebtObligation],
        rent: float,
        stock_price: float,
        ytd_income: float
    ) -> tuple[MonthlySnapshot, float]:
        """Simulate a month in the renting scenario. Returns snapshot and updated YTD income."""
        monthly_salary = income_profile.monthly_salary
        bonus = income_profile.bonus if month == 12 else 0
        gross_income = monthly_salary + bonus
        ytd_income += gross_income

        # Process RSU vests with sell-to-cover (same as buying scenario)
        vest_income = 0.0
        for vest in self.inputs.future_rsu_vests:
            if (vest.vest_date.year == year and vest.vest_date.month == month):
                this_vest_value = vest.shares * stock_price
                vest_income += this_vest_value
                ytd_income += this_vest_value  # Add just this vest, not cumulative

                # Sell-to-cover: only keep shares after withholding
                shares_after_withholding = int(vest.shares * (1 - RSU_VEST_WITHHOLDING_RATE))

                if shares_after_withholding > 0:
                    new_lot = RSULot(
                        lot_id=vest.vest_id,
                        shares=shares_after_withholding,
                        cost_basis_per_share=stock_price,
                        vest_date=vest.vest_date
                    )
                    rsu_holdings.append(new_lot)

        # Process RSU sales (same strategies as buying, except SELL_AT_PURCHASE)
        sale_proceeds = 0.0
        sale_gains = 0.0
        sale_taxes = 0.0

        for rule in self.inputs.rsu_sell_rules:
            # Skip SELL_AT_PURCHASE since there's no home purchase
            if rule.strategy == RSUSellStrategy.SELL_AT_PURCHASE:
                continue

            lots_to_process = []
            if rule.lot_id == "all":
                lots_to_process = [lot for lot in rsu_holdings if lot.shares > 0]
            else:
                lots_to_process = [lot for lot in rsu_holdings
                                   if lot.lot_id == rule.lot_id and lot.shares > 0]

            for lot in lots_to_process:
                should_sell = False

                if rule.strategy == RSUSellStrategy.SELL_IMMEDIATELY:
                    if (lot.vest_date.year == year and lot.vest_date.month == month):
                        should_sell = True
                elif rule.strategy == RSUSellStrategy.SELL_LONG_TERM:
                    lt_date = lot.vest_date + relativedelta(years=1)
                    if (lt_date.year == year and lt_date.month == month):
                        should_sell = True
                elif rule.strategy == RSUSellStrategy.CUSTOM and rule.sell_date:
                    if (rule.sell_date.year == year and rule.sell_date.month == month):
                        should_sell = True

                if should_sell:
                    shares_to_sell = rule.shares_to_sell or lot.shares
                    shares_to_sell = min(shares_to_sell, lot.shares)

                    if shares_to_sell > 0:
                        proceeds = shares_to_sell * stock_price
                        cost_basis = shares_to_sell * lot.cost_basis_per_share
                        gain = proceeds - cost_basis

                        term = lot.get_term(current_date)
                        tax = self._calculate_rsu_sale_tax(gain, term, ytd_income)

                        sale_proceeds += proceeds
                        sale_gains += gain
                        sale_taxes += tax
                        lot.shares -= shares_to_sell

        # Taxes
        tax_rate = self._estimate_tax_rate(income_profile.total_annual)
        income_tax = gross_income * tax_rate

        # Note: RSU vest withholding handled via sell-to-cover (reduced shares above)

        # Calculate and apply debt payments
        other_debt = 0.0
        for debt in debts:
            if debt.remaining_balance > 0:
                monthly_interest = debt.remaining_balance * (debt.interest_rate / 12)
                principal_payment = debt.monthly_payment - monthly_interest
                if principal_payment > debt.remaining_balance:
                    principal_payment = debt.remaining_balance
                    actual_payment = principal_payment + monthly_interest
                else:
                    actual_payment = debt.monthly_payment
                debt.remaining_balance -= principal_payment
                other_debt += actual_payment
            elif debt.remaining_balance == 0 and debt.interest_rate == 0:
                other_debt += debt.monthly_payment

        # Apply cash flow
        net_flow = (gross_income + sale_proceeds - rent - other_debt - income_tax -
                    sale_taxes - self.inputs.monthly_living_expenses)
        cash += net_flow

        # Grow investments
        for inv in investments:
            monthly_return = (1 + inv.annual_return) ** (1/12) - 1
            inv.balance *= (1 + monthly_return)

        # RSU value
        rsu_value = sum(lot.shares * stock_price for lot in rsu_holdings)

        snapshot = MonthlySnapshot(
            date=current_date,
            year=year,
            month=month,
            gross_income=gross_income,
            rsu_vest_income=vest_income,
            rsu_sale_proceeds=sale_proceeds,
            rsu_sale_gains=sale_gains,
            cash_balance=cash,
            investment_balance=sum(inv.balance for inv in investments),
            rsu_holdings_value=rsu_value,
            home_equity=0,
            mortgage_principal=0,
            mortgage_interest=0,
            property_tax=0,
            homeowners_insurance=0,
            pmi=0,
            hoa=0,
            maintenance=0,
            rent=rent,
            other_debt_payments=other_debt,
            income_tax_withheld=income_tax,
            living_expenses=self.inputs.monthly_living_expenses,
            capital_gains_tax_paid=sale_taxes
        )
        return snapshot, ytd_income

    def _build_yearly_summaries(
        self,
        monthly_snapshots: list[MonthlySnapshot]
    ) -> list[YearlySummary]:
        """Build yearly summaries from monthly snapshots."""
        by_year: dict[int, list[MonthlySnapshot]] = {}

        for snapshot in monthly_snapshots:
            if snapshot.year not in by_year:
                by_year[snapshot.year] = []
            by_year[snapshot.year].append(snapshot)

        return [
            YearlySummary(year=year, months=months)
            for year, months in sorted(by_year.items())
        ]


# =============================================================================
# OUTPUT AND ANALYSIS FUNCTIONS
# =============================================================================

def print_simulation_summary(result: SimulationResult) -> None:
    """Print comprehensive simulation summary."""
    print("\n" + "=" * 80)
    print("FINANCIAL SIMULATION RESULTS")
    print("=" * 80)

    inputs = result.inputs
    if inputs.house_plan:
        hp = inputs.house_plan
        print(f"\nHome Purchase Plan:")
        print(f"  Purchase Date: {hp.purchase_date}")
        print(f"  Home Price: ${hp.home_price:,.0f}")
        print(f"  Down Payment: {hp.down_payment_percent*100:.0f}% (${hp.down_payment:,.0f})")
        print(f"  Mortgage Rate: {hp.mortgage_rate*100:.2f}%")
        print(f"  Loan Term: {hp.loan_term_years} years")

    print(f"\nSimulation Period: {inputs.simulation_years} years")
    print(f"Starting Cash: ${inputs.initial_cash:,.0f}")

    # Yearly summary table
    print("\n" + "-" * 80)
    print("YEAR-BY-YEAR CASH FLOW")
    print("-" * 80)
    print(f"{'Year':<6} {'Income':>12} {'Housing':>12} {'Cash Flow':>12} "
          f"{'Net Worth':>12} {'vs Rent':>12}")
    print("-" * 80)

    for i, yearly in enumerate(result.yearly_summaries):
        rent_nw = result.rent_scenario_snapshots[min((i+1)*12-1, len(result.rent_scenario_snapshots)-1)].net_worth
        vs_rent = yearly.end_of_year_net_worth - rent_nw

        print(
            f"{yearly.year:<6} "
            f"${yearly.total_income:>10,.0f} "
            f"${yearly.total_housing_cost:>10,.0f} "
            f"${yearly.total_net_cash_flow:>10,.0f} "
            f"${yearly.end_of_year_net_worth:>10,.0f} "
            f"{'':>1}${vs_rent:>+10,.0f}"
        )

    # Cash flow analysis
    print("\n" + "-" * 80)
    print("MONTHLY CASH FLOW SUMMARY")
    print("-" * 80)

    negative_months = [s for s in result.monthly_snapshots if s.net_cash_flow < 0]
    if negative_months:
        print(f"\nWARNING: {len(negative_months)} months with negative cash flow:")
        for s in negative_months[:5]:
            print(f"  {s.year}-{s.month:02d}: ${s.net_cash_flow:,.0f}")
        if len(negative_months) > 5:
            print(f"  ... and {len(negative_months) - 5} more")
    else:
        print("\nAll months have positive cash flow.")

    print("\nAverage Monthly Cash Flow by Year:")
    for yearly in result.yearly_summaries:
        print(f"  {yearly.year}: ${yearly.average_monthly_cash_flow:,.0f}/month")

    # Net worth trajectory
    print("\n" + "-" * 80)
    print("NET WORTH TRAJECTORY")
    print("-" * 80)

    print(f"\n{'Year':<6} {'Cash':>12} {'Investments':>12} {'RSUs':>12} "
          f"{'Home Equity':>12} {'Total':>12}")
    print("-" * 80)

    for yearly in result.yearly_summaries:
        end = yearly.months[-1]
        print(
            f"{yearly.year:<6} "
            f"${end.cash_balance:>10,.0f} "
            f"${end.investment_balance:>10,.0f} "
            f"${end.rsu_holdings_value:>10,.0f} "
            f"${end.home_equity:>10,.0f} "
            f"${end.net_worth:>10,.0f}"
        )

    # Breakeven analysis
    print("\n" + "-" * 80)
    print("BREAKEVEN ANALYSIS (Buying vs Renting)")
    print("-" * 80)

    if result.breakeven_month is not None:
        years = result.breakeven_month // 12
        months = result.breakeven_month % 12
        print(f"\nBreakeven reached after: {years} years, {months} months")
    else:
        print(f"\nBreakeven NOT reached within {inputs.simulation_years} years")

    # Compare at different points
    print("\nNet Worth Comparison (Buying vs Renting):")
    print(f"{'Year':<6} {'Buying':>14} {'Renting':>14} {'Difference':>14}")

    for i, yearly in enumerate(result.yearly_summaries):
        month_idx = min((i+1)*12-1, len(result.monthly_snapshots)-1)
        buy_nw = result.monthly_snapshots[month_idx].net_worth
        rent_nw = result.rent_scenario_snapshots[month_idx].net_worth
        diff = buy_nw - rent_nw

        print(
            f"{yearly.year:<6} "
            f"${buy_nw:>12,.0f} "
            f"${rent_nw:>12,.0f} "
            f"${diff:>+12,.0f}"
        )

    # Key events
    print("\n" + "-" * 80)
    print("KEY EVENTS")
    print("-" * 80)

    if result.home_purchase_month is not None:
        m = result.monthly_snapshots[result.home_purchase_month]
        print(f"  Home Purchased: {m.year}-{m.month:02d}")

    if result.pmi_removal_month is not None:
        m = result.monthly_snapshots[result.pmi_removal_month]
        print(f"  PMI Removed: {m.year}-{m.month:02d}")

    # Totals
    print("\n" + "-" * 80)
    print("TOTALS OVER SIMULATION PERIOD")
    print("-" * 80)
    print(f"  Total Housing Costs: ${result.total_housing_costs:,.0f}")
    print(f"  Total Mortgage Interest: ${result.total_mortgage_interest:,.0f}")
    print(f"  Total PMI Paid: ${result.total_pmi_paid:,.0f}")
    print(f"  Total RSU Taxes Paid: ${result.total_rsu_taxes_paid:,.0f}")
    print(f"  Final Net Worth (Buying): ${result.final_net_worth:,.0f}")
    print(f"  Final Net Worth (Renting): ${result.rent_scenario_final_net_worth:,.0f}")


def print_monthly_detail(result: SimulationResult, year: int) -> None:
    """Print detailed monthly breakdown for a specific year."""
    yearly = next((y for y in result.yearly_summaries if y.year == year), None)
    if not yearly:
        print(f"No data for year {year}")
        return

    print(f"\n{'=' * 100}")
    print(f"MONTHLY DETAIL FOR {year}")
    print(f"{'=' * 100}")

    print(f"\n{'Mon':<4} {'Income':>10} {'Housing':>10} {'P&I':>10} "
          f"{'Tax+Ins':>10} {'Other':>10} {'Cash Flow':>10} {'Net Worth':>12}")
    print("-" * 100)

    for m in yearly.months:
        pi = m.mortgage_principal + m.mortgage_interest
        tax_ins = m.property_tax + m.homeowners_insurance + m.pmi
        other = m.other_debt_payments + m.income_tax_withheld + m.living_expenses
        housing = m.total_housing_cost

        print(
            f"{m.month:<4} "
            f"${m.gross_income:>8,.0f} "
            f"${housing:>8,.0f} "
            f"${pi:>8,.0f} "
            f"${tax_ins:>8,.0f} "
            f"${other:>8,.0f} "
            f"${m.net_cash_flow:>8,.0f} "
            f"${m.net_worth:>10,.0f}"
        )

    print("-" * 100)
    print(
        f"{'TOT':<4} "
        f"${yearly.total_income:>8,.0f} "
        f"${yearly.total_housing_cost:>8,.0f} "
        f"${sum(m.mortgage_principal + m.mortgage_interest for m in yearly.months):>8,.0f} "
        f"${sum(m.property_tax + m.homeowners_insurance + m.pmi for m in yearly.months):>8,.0f} "
        f"${sum(m.other_debt_payments + m.income_tax_withheld + m.living_expenses for m in yearly.months):>8,.0f} "
        f"${yearly.total_net_cash_flow:>8,.0f} "
        f"${yearly.end_of_year_net_worth:>10,.0f}"
    )


def print_cash_flow_chart(result: SimulationResult) -> None:
    """Print ASCII chart of monthly cash flow."""
    print("\n" + "=" * 80)
    print("MONTHLY CASH FLOW CHART")
    print("=" * 80)

    max_flow = max(abs(s.net_cash_flow) for s in result.monthly_snapshots)
    scale = 40 / max_flow if max_flow > 0 else 1

    for yearly in result.yearly_summaries:
        print(f"\n{yearly.year}:")
        for m in yearly.months:
            bar_len = int(abs(m.net_cash_flow) * scale)
            if m.net_cash_flow >= 0:
                bar = "█" * bar_len
                print(f"  {m.month:2d} |{'':>40}{bar} ${m.net_cash_flow:,.0f}")
            else:
                bar = "█" * bar_len
                padding = 40 - bar_len
                print(f"  {m.month:2d} |{'':<{padding}}{bar}| -${abs(m.net_cash_flow):,.0f}")


def export_to_csv(result: SimulationResult, filename: str) -> None:
    """Export simulation results to CSV."""
    import csv

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Year', 'Month', 'Gross Income', 'RSU Vest Income', 'RSU Sale Proceeds',
            'Mortgage Principal', 'Mortgage Interest', 'Property Tax', 'Insurance',
            'PMI', 'HOA', 'Maintenance', 'Rent', 'Other Debt', 'Income Tax',
            'Living Expenses', 'Cap Gains Tax', 'Total Housing', 'Net Cash Flow',
            'Cash Balance', 'Investment Balance', 'RSU Value', 'Home Equity', 'Net Worth',
            'Rent Scenario Net Worth'
        ])

        for i, m in enumerate(result.monthly_snapshots):
            rent_m = result.rent_scenario_snapshots[i]
            writer.writerow([
                m.year, m.month, m.gross_income, m.rsu_vest_income, m.rsu_sale_proceeds,
                m.mortgage_principal, m.mortgage_interest, m.property_tax,
                m.homeowners_insurance, m.pmi, m.hoa, m.maintenance, m.rent,
                m.other_debt_payments, m.income_tax_withheld, m.living_expenses,
                m.capital_gains_tax_paid, m.total_housing_cost, m.net_cash_flow,
                m.cash_balance, m.investment_balance, m.rsu_holdings_value,
                m.home_equity, m.net_worth, rent_m.net_worth
            ])

    print(f"Exported to {filename}")
