"""
Closing costs calculator.

Handles all upfront costs associated with purchasing a home.
"""

from dataclasses import dataclass
from config import PropertyInputs, ClosingCostInputs


@dataclass
class ClosingCostBreakdown:
    """Detailed breakdown of closing costs."""
    # Loan-related costs
    loan_origination_fee: float
    appraisal_fee: float
    credit_report_fee: float
    underwriting_fee: float

    # Title and escrow
    title_insurance: float
    escrow_fee: float
    recording_fees: float

    # Prepaid items
    prepaid_property_tax: float
    prepaid_homeowners_insurance: float
    prepaid_interest: float

    # Other
    other_fees: float

    @property
    def total_loan_costs(self) -> float:
        return (
            self.loan_origination_fee
            + self.appraisal_fee
            + self.credit_report_fee
            + self.underwriting_fee
        )

    @property
    def total_title_escrow(self) -> float:
        return self.title_insurance + self.escrow_fee + self.recording_fees

    @property
    def total_prepaids(self) -> float:
        return (
            self.prepaid_property_tax
            + self.prepaid_homeowners_insurance
            + self.prepaid_interest
        )

    @property
    def total_closing_costs(self) -> float:
        return (
            self.total_loan_costs
            + self.total_title_escrow
            + self.total_prepaids
            + self.other_fees
        )


@dataclass
class TotalCashNeeded:
    """Total cash needed at closing."""
    down_payment: float
    closing_costs: float
    reserves_recommended: float  # 2-6 months of payments recommended

    @property
    def minimum_cash_needed(self) -> float:
        """Minimum cash to close (down payment + closing costs)."""
        return self.down_payment + self.closing_costs

    @property
    def recommended_cash_needed(self) -> float:
        """Recommended cash including reserves."""
        return self.minimum_cash_needed + self.reserves_recommended


class ClosingCostCalculator:
    """Calculator for closing costs and cash needed."""

    def __init__(
        self,
        property_inputs: PropertyInputs,
        closing_inputs: ClosingCostInputs
    ):
        self.property = property_inputs
        self.closing = closing_inputs

    def calculate_closing_costs(
        self,
        days_of_prepaid_interest: int = 15
    ) -> ClosingCostBreakdown:
        """
        Calculate detailed closing costs.

        Args:
            days_of_prepaid_interest: Days of interest to prepay (depends on closing date)
        """
        loan_amount = self.property.loan_amount

        # Loan-related costs
        origination = loan_amount * self.closing.loan_origination_percent
        appraisal = self.closing.appraisal_fee
        credit_report = 50.0  # Typical credit report fee
        underwriting = 500.0  # Typical underwriting fee

        # Title and escrow
        title_insurance = self.property.home_price * self.closing.title_insurance_percent
        escrow_fee = self.closing.escrow_fee
        recording = self.closing.recording_fees

        # Prepaid items
        monthly_property_tax = (
            self.property.home_price
            * self.property.property_tax_rate
            / 12
        )
        prepaid_tax = monthly_property_tax * self.closing.prepaid_property_tax_months

        monthly_insurance = self.property.homeowners_insurance_annual / 12
        prepaid_insurance = monthly_insurance * self.closing.prepaid_insurance_months

        # Prepaid interest (per diem)
        daily_interest = (
            loan_amount
            * self.property.mortgage_rate
            / 365
        )
        prepaid_interest = daily_interest * days_of_prepaid_interest

        return ClosingCostBreakdown(
            loan_origination_fee=origination,
            appraisal_fee=appraisal,
            credit_report_fee=credit_report,
            underwriting_fee=underwriting,
            title_insurance=title_insurance,
            escrow_fee=escrow_fee,
            recording_fees=recording,
            prepaid_property_tax=prepaid_tax,
            prepaid_homeowners_insurance=prepaid_insurance,
            prepaid_interest=prepaid_interest,
            other_fees=self.closing.other_fees
        )

    def calculate_total_cash_needed(
        self,
        months_of_reserves: int = 3,
        days_of_prepaid_interest: int = 15
    ) -> TotalCashNeeded:
        """
        Calculate total cash needed at closing.

        Args:
            months_of_reserves: Months of payment reserves to maintain
            days_of_prepaid_interest: Days of interest to prepay
        """
        closing_costs = self.calculate_closing_costs(days_of_prepaid_interest)

        # Calculate monthly payment for reserves
        from mortgage_calculator import MortgageCalculator
        mortgage_calc = MortgageCalculator(self.property)
        monthly_breakdown = mortgage_calc.calculate_monthly_breakdown()
        monthly_payment = monthly_breakdown.total_monthly

        reserves = monthly_payment * months_of_reserves

        return TotalCashNeeded(
            down_payment=self.property.down_payment,
            closing_costs=closing_costs.total_closing_costs,
            reserves_recommended=reserves
        )

    def estimate_closing_costs_range(self) -> tuple[float, float]:
        """
        Estimate range of closing costs (low and high).

        Returns:
            Tuple of (low_estimate, high_estimate)
        """
        loan_amount = self.property.loan_amount

        # Low estimate: 2% of loan amount
        low = loan_amount * 0.02

        # High estimate: 5% of loan amount
        high = loan_amount * 0.05

        return low, high


def estimate_seller_credits(
    home_price: float,
    max_credit_percent: float = 0.03
) -> float:
    """
    Estimate potential seller credits toward closing costs.

    Many sellers will contribute to closing costs, especially
    in a buyer's market. Typically capped at 3-6% depending
    on loan type and down payment.

    Args:
        home_price: Purchase price
        max_credit_percent: Maximum seller credit as percent

    Returns:
        Maximum potential seller credit
    """
    return home_price * max_credit_percent
