"""
Configuration and data classes for the Home Affordability Calculator.

This module defines all input structures for the simulation.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class FilingStatus(Enum):
    """Tax filing status."""
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"


class RSUTerm(Enum):
    """RSU holding period for tax purposes."""
    SHORT_TERM = "short_term"  # Held less than 1 year
    LONG_TERM = "long_term"    # Held 1 year or more


class InvestmentType(Enum):
    """Types of investments."""
    MONEY_MARKET = "money_market"
    CD = "cd"
    BONDS = "bonds"
    ETFS = "etfs"
    STOCKS = "stocks"
    MANAGED_ACCOUNT = "managed_account"


@dataclass
class IncomeSchedule:
    """
    Annual income schedule.

    Attributes:
        year: The calendar year
        gross_annual_income: Gross annual income for that year
        bonus: Expected bonus (optional)
        other_income: Other taxable income (optional)
    """
    year: int
    gross_annual_income: float
    bonus: float = 0.0
    other_income: float = 0.0

    @property
    def total_income(self) -> float:
        return self.gross_annual_income + self.bonus + self.other_income


@dataclass
class RSUGrant:
    """
    A single RSU grant/lot.

    Attributes:
        grant_id: Unique identifier for this grant
        quantity: Number of shares
        cost_basis_per_share: Cost basis per share (price at vesting)
        cost_basis_total: Total cost basis (quantity * cost_basis_per_share)
        grant_date: Date the RSU was granted
        vest_date: Date the RSU vested (when you received the shares)
        sale_available_date: Earliest date you can sell (may be same as vest_date)
    """
    grant_id: str
    quantity: int
    cost_basis_per_share: float
    vest_date: date
    grant_date: Optional[date] = None
    sale_available_date: Optional[date] = None

    def __post_init__(self):
        if self.sale_available_date is None:
            self.sale_available_date = self.vest_date

    @property
    def cost_basis_total(self) -> float:
        return self.quantity * self.cost_basis_per_share

    def get_term(self, sale_date: date) -> RSUTerm:
        """Determine if this is short-term or long-term based on sale date."""
        holding_period = (sale_date - self.vest_date).days
        if holding_period >= 365:
            return RSUTerm.LONG_TERM
        return RSUTerm.SHORT_TERM

    def calculate_gain(self, sale_price_per_share: float) -> float:
        """Calculate capital gain/loss for this lot."""
        sale_proceeds = self.quantity * sale_price_per_share
        return sale_proceeds - self.cost_basis_total


@dataclass
class StockPriceProjection:
    """
    Stock price projection for a specific date.

    Attributes:
        date: The projection date
        price: Projected stock price
        scenario: Optional label (e.g., "optimistic", "base", "pessimistic")
    """
    date: date
    price: float
    scenario: str = "base"


@dataclass
class Investment:
    """
    A non-RSU investment holding.

    Attributes:
        name: Description of the investment
        investment_type: Type of investment
        current_value: Current market value
        cost_basis: Original cost (for tax calculations)
        annual_return_rate: Expected annual return rate (e.g., 0.05 for 5%)
        is_liquid: Whether it can be easily converted to cash
        maturity_date: For CDs, when it matures
        early_withdrawal_penalty_months: For CDs, penalty in months of interest
    """
    name: str
    investment_type: InvestmentType
    current_value: float
    cost_basis: float = 0.0
    annual_return_rate: float = 0.0
    is_liquid: bool = True
    maturity_date: Optional[date] = None
    early_withdrawal_penalty_months: int = 0

    def __post_init__(self):
        # If cost basis not provided, assume it equals current value (no gain)
        if self.cost_basis == 0.0:
            self.cost_basis = self.current_value

    @property
    def unrealized_gain(self) -> float:
        return self.current_value - self.cost_basis

    def calculate_early_withdrawal_penalty(self) -> float:
        """Calculate CD early withdrawal penalty."""
        if self.investment_type != InvestmentType.CD:
            return 0.0
        monthly_interest = self.current_value * (self.annual_return_rate / 12)
        return monthly_interest * self.early_withdrawal_penalty_months


@dataclass
class PropertyInputs:
    """
    Property and mortgage inputs.

    Attributes:
        home_price: Purchase price of the home
        down_payment_percent: Down payment as percentage (e.g., 0.20 for 20%)
        down_payment_amount: Alternatively, specify exact amount
        mortgage_rate: Annual interest rate (e.g., 0.07 for 7%)
        loan_term_years: Loan term (typically 15 or 30)
        property_tax_rate: Annual property tax rate (e.g., 0.0125 for 1.25%)
        hoa_monthly: Monthly HOA fees
        homeowners_insurance_annual: Annual homeowners insurance premium
        pmi_rate: PMI rate if down payment < 20% (e.g., 0.005 for 0.5%)
    """
    home_price: float
    mortgage_rate: float
    loan_term_years: int = 30
    down_payment_percent: Optional[float] = None
    down_payment_amount: Optional[float] = None
    property_tax_rate: float = 0.0125  # California average ~1.25% with assessments
    hoa_monthly: float = 0.0
    homeowners_insurance_annual: float = 1500.0
    pmi_rate: float = 0.005  # 0.5% annually

    def __post_init__(self):
        # Must specify either percent or amount
        if self.down_payment_percent is None and self.down_payment_amount is None:
            self.down_payment_percent = 0.20  # Default to 20%

    @property
    def down_payment(self) -> float:
        if self.down_payment_amount is not None:
            return self.down_payment_amount
        return self.home_price * self.down_payment_percent

    @property
    def loan_amount(self) -> float:
        return self.home_price - self.down_payment

    @property
    def ltv_ratio(self) -> float:
        """Loan-to-value ratio."""
        return self.loan_amount / self.home_price

    @property
    def requires_pmi(self) -> bool:
        """PMI required if down payment < 20%."""
        return self.ltv_ratio > 0.80


@dataclass
class ClosingCostInputs:
    """
    Closing cost inputs.

    Attributes:
        loan_origination_percent: Origination fee as percent of loan
        appraisal_fee: Appraisal cost
        title_insurance_percent: Title insurance as percent of home price
        escrow_fee: Escrow/settlement fee
        recording_fees: Government recording fees
        other_fees: Other miscellaneous fees
    """
    loan_origination_percent: float = 0.01  # 1% of loan
    appraisal_fee: float = 500.0
    title_insurance_percent: float = 0.005  # 0.5% of home price
    escrow_fee: float = 2000.0
    recording_fees: float = 200.0
    prepaid_property_tax_months: int = 2  # Months of property tax to prepay
    prepaid_insurance_months: int = 12  # Months of insurance to prepay
    other_fees: float = 1000.0


@dataclass
class DebtItem:
    """
    Existing debt for DTI calculations.

    Attributes:
        name: Description of the debt
        monthly_payment: Required monthly payment
        balance: Remaining balance (optional, for payoff scenarios)
        interest_rate: Annual interest rate
    """
    name: str
    monthly_payment: float
    balance: float = 0.0
    interest_rate: float = 0.0


@dataclass
class SimulationConfig:
    """
    Master configuration for the simulation.

    Attributes:
        filing_status: Tax filing status
        state: State of residence (for tax calculations)
        income_schedule: List of annual income projections
        rsu_grants: List of RSU grants/lots
        stock_current_price: Current stock price
        stock_projections: List of future stock price projections
        cash_savings: Current cash in bank
        investments: List of other investments
        existing_debts: List of existing debt obligations
        property_inputs: Property and mortgage details
        closing_cost_inputs: Closing cost details
        target_purchase_date: When you plan to buy
    """
    filing_status: FilingStatus
    income_schedule: list[IncomeSchedule]
    rsu_grants: list[RSUGrant]
    stock_symbol: str
    stock_current_price: float
    stock_projections: list[StockPriceProjection]
    cash_savings: float
    investments: list[Investment]
    property_inputs: PropertyInputs
    state: str = "CA"
    existing_debts: list[DebtItem] = field(default_factory=list)
    closing_cost_inputs: ClosingCostInputs = field(default_factory=ClosingCostInputs)
    target_purchase_date: Optional[date] = None

    def get_income_for_year(self, year: int) -> Optional[IncomeSchedule]:
        """Get income schedule for a specific year."""
        for income in self.income_schedule:
            if income.year == year:
                return income
        return None

    def get_stock_price_on_date(self, target_date: date, scenario: str = "base") -> float:
        """Get projected stock price for a given date and scenario."""
        # Find the closest projection on or before the target date
        matching_projections = [
            p for p in self.stock_projections
            if p.scenario == scenario and p.date <= target_date
        ]
        if not matching_projections:
            return self.stock_current_price

        # Return the most recent projection
        return max(matching_projections, key=lambda p: p.date).price

    @property
    def total_liquid_assets(self) -> float:
        """Total cash and liquid investments."""
        liquid_investments = sum(
            inv.current_value for inv in self.investments if inv.is_liquid
        )
        return self.cash_savings + liquid_investments

    @property
    def total_rsu_value(self) -> float:
        """Total current value of all RSU holdings."""
        return sum(
            grant.quantity * self.stock_current_price
            for grant in self.rsu_grants
        )
