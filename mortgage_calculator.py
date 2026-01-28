"""
Mortgage calculator module.

Handles:
- Monthly payment calculation (P&I)
- Amortization schedule
- PMI calculations
- Total cost of loan
"""

from dataclasses import dataclass
from typing import Optional
from config import PropertyInputs


@dataclass
class MonthlyPaymentBreakdown:
    """Monthly payment breakdown."""
    principal: float
    interest: float
    property_tax: float
    homeowners_insurance: float
    pmi: float
    hoa: float

    @property
    def principal_and_interest(self) -> float:
        return self.principal + self.interest

    @property
    def total_piti(self) -> float:
        """Principal, Interest, Taxes, Insurance."""
        return (
            self.principal
            + self.interest
            + self.property_tax
            + self.homeowners_insurance
        )

    @property
    def total_monthly(self) -> float:
        """Total monthly housing payment."""
        return self.total_piti + self.pmi + self.hoa


@dataclass
class AmortizationEntry:
    """Single month in amortization schedule."""
    month: int
    payment: float
    principal: float
    interest: float
    pmi: float
    remaining_balance: float
    cumulative_interest: float
    cumulative_principal: float
    equity_percent: float


@dataclass
class MortgageSummary:
    """Summary of mortgage calculations."""
    loan_amount: float
    monthly_pi: float  # Principal and interest only
    monthly_piti: float  # P&I + taxes + insurance
    total_monthly_payment: float  # Including PMI and HOA
    total_interest_paid: float
    total_pmi_paid: float
    months_until_pmi_removed: Optional[int]
    total_cost_of_loan: float
    effective_interest_rate: float  # Including PMI


class MortgageCalculator:
    """Calculator for mortgage payments and amortization."""

    def __init__(self, property_inputs: PropertyInputs):
        self.property = property_inputs

    def calculate_monthly_pi(
        self,
        loan_amount: Optional[float] = None,
        annual_rate: Optional[float] = None,
        term_years: Optional[int] = None
    ) -> float:
        """
        Calculate monthly principal and interest payment.

        Uses the standard amortization formula:
        M = P * [r(1+r)^n] / [(1+r)^n - 1]

        Where:
        - M = monthly payment
        - P = principal (loan amount)
        - r = monthly interest rate
        - n = total number of payments
        """
        principal = loan_amount or self.property.loan_amount
        annual_rate = annual_rate or self.property.mortgage_rate
        term_years = term_years or self.property.loan_term_years

        if annual_rate == 0:
            return principal / (term_years * 12)

        monthly_rate = annual_rate / 12
        num_payments = term_years * 12

        # Amortization formula
        payment = principal * (
            (monthly_rate * (1 + monthly_rate) ** num_payments)
            / ((1 + monthly_rate) ** num_payments - 1)
        )

        return payment

    def calculate_monthly_property_tax(self) -> float:
        """Calculate monthly property tax."""
        annual_tax = self.property.home_price * self.property.property_tax_rate
        return annual_tax / 12

    def calculate_monthly_insurance(self) -> float:
        """Calculate monthly homeowners insurance."""
        return self.property.homeowners_insurance_annual / 12

    def calculate_monthly_pmi(
        self,
        current_balance: Optional[float] = None
    ) -> float:
        """
        Calculate monthly PMI.

        PMI is typically required when LTV > 80%.
        Can be removed once LTV reaches 78-80%.
        """
        if not self.property.requires_pmi:
            return 0.0

        balance = current_balance or self.property.loan_amount
        current_ltv = balance / self.property.home_price

        # PMI removed when LTV reaches 78%
        if current_ltv <= 0.78:
            return 0.0

        annual_pmi = balance * self.property.pmi_rate
        return annual_pmi / 12

    def calculate_monthly_breakdown(
        self,
        month: int = 1,
        remaining_balance: Optional[float] = None
    ) -> MonthlyPaymentBreakdown:
        """
        Calculate detailed monthly payment breakdown.

        Args:
            month: Which month of the loan (1-indexed)
            remaining_balance: Current loan balance (for PMI calculation)
        """
        balance = remaining_balance or self.property.loan_amount
        monthly_rate = self.property.mortgage_rate / 12

        # Interest for this month
        interest = balance * monthly_rate

        # Total P&I payment (fixed)
        total_pi = self.calculate_monthly_pi()

        # Principal is what's left after interest
        principal = total_pi - interest

        return MonthlyPaymentBreakdown(
            principal=principal,
            interest=interest,
            property_tax=self.calculate_monthly_property_tax(),
            homeowners_insurance=self.calculate_monthly_insurance(),
            pmi=self.calculate_monthly_pmi(balance),
            hoa=self.property.hoa_monthly
        )

    def generate_amortization_schedule(
        self,
        num_months: Optional[int] = None
    ) -> list[AmortizationEntry]:
        """
        Generate full amortization schedule.

        Args:
            num_months: Number of months to generate (default: full term)

        Returns:
            List of AmortizationEntry for each month
        """
        term_months = self.property.loan_term_years * 12
        num_months = num_months or term_months

        schedule = []
        balance = self.property.loan_amount
        monthly_rate = self.property.mortgage_rate / 12
        monthly_pi = self.calculate_monthly_pi()

        cumulative_interest = 0.0
        cumulative_principal = 0.0

        for month in range(1, min(num_months + 1, term_months + 1)):
            # Interest for this month
            interest = balance * monthly_rate
            principal = monthly_pi - interest

            # PMI for this month
            pmi = self.calculate_monthly_pmi(balance)

            # Update balance
            balance = max(0, balance - principal)

            cumulative_interest += interest
            cumulative_principal += principal

            # Equity percentage
            equity_percent = 1 - (balance / self.property.home_price)

            schedule.append(AmortizationEntry(
                month=month,
                payment=monthly_pi,
                principal=principal,
                interest=interest,
                pmi=pmi,
                remaining_balance=balance,
                cumulative_interest=cumulative_interest,
                cumulative_principal=cumulative_principal,
                equity_percent=equity_percent
            ))

        return schedule

    def calculate_mortgage_summary(self) -> MortgageSummary:
        """Calculate comprehensive mortgage summary."""
        schedule = self.generate_amortization_schedule()

        # Calculate totals from schedule
        total_interest = sum(entry.interest for entry in schedule)
        total_pmi = sum(entry.pmi for entry in schedule)

        # Find when PMI is removed
        months_until_pmi_removed = None
        if self.property.requires_pmi:
            for entry in schedule:
                if entry.pmi == 0:
                    months_until_pmi_removed = entry.month
                    break

        # Monthly payment components
        first_month = self.calculate_monthly_breakdown(month=1)
        monthly_pi = first_month.principal_and_interest
        monthly_piti = first_month.total_piti
        total_monthly = first_month.total_monthly

        # Total cost of loan
        total_cost = (
            self.property.loan_amount
            + total_interest
            + total_pmi
        )

        # Effective interest rate (including PMI)
        # APR-like calculation
        total_payments = sum(entry.payment + entry.pmi for entry in schedule)
        effective_rate = self._calculate_effective_rate(
            self.property.loan_amount,
            total_payments,
            len(schedule)
        )

        return MortgageSummary(
            loan_amount=self.property.loan_amount,
            monthly_pi=monthly_pi,
            monthly_piti=monthly_piti,
            total_monthly_payment=total_monthly,
            total_interest_paid=total_interest,
            total_pmi_paid=total_pmi,
            months_until_pmi_removed=months_until_pmi_removed,
            total_cost_of_loan=total_cost,
            effective_interest_rate=effective_rate
        )

    def _calculate_effective_rate(
        self,
        principal: float,
        total_payments: float,
        num_months: int
    ) -> float:
        """
        Calculate effective annual interest rate using Newton's method.

        This gives an APR-like rate that accounts for PMI.
        """
        monthly_payment = total_payments / num_months

        # Initial guess
        rate = self.property.mortgage_rate / 12

        # Newton's method iterations
        for _ in range(100):
            # Calculate payment at current rate
            if rate == 0:
                calc_payment = principal / num_months
            else:
                calc_payment = principal * (
                    (rate * (1 + rate) ** num_months)
                    / ((1 + rate) ** num_months - 1)
                )

            # Calculate derivative
            if rate == 0:
                derivative = -principal * num_months / 2
            else:
                term1 = (1 + rate) ** num_months
                term2 = (1 + rate) ** (num_months - 1)
                numerator = term1 + rate * num_months * term2
                denominator = (term1 - 1) ** 2
                derivative = principal * (
                    (numerator * (term1 - 1) - (rate * term1) * num_months * term2)
                    / denominator
                )

            # Update rate
            if derivative == 0:
                break
            new_rate = rate - (calc_payment - monthly_payment) / derivative

            if abs(new_rate - rate) < 1e-10:
                break
            rate = max(0, new_rate)

        return rate * 12  # Convert to annual

    def calculate_interest_paid_in_year(
        self,
        year: int,
        start_month: int = 1
    ) -> float:
        """
        Calculate total interest paid in a calendar year.

        Useful for tax deduction calculations.

        Args:
            year: Which year of the loan (1-indexed)
            start_month: Month of year when loan started (1=January)
        """
        schedule = self.generate_amortization_schedule()

        # Calculate month range for this year
        if year == 1:
            # First year: from start_month to December
            first_month = 1
            last_month = 13 - start_month
        else:
            # Subsequent years: full 12 months
            months_in_year_1 = 13 - start_month
            first_month = months_in_year_1 + (year - 2) * 12 + 1
            last_month = first_month + 11

        # Sum interest for those months
        interest = sum(
            entry.interest
            for entry in schedule
            if first_month <= entry.month <= last_month
        )

        return interest

    def compare_loan_terms(
        self,
        terms: list[int] = [15, 30]
    ) -> dict[int, MortgageSummary]:
        """
        Compare different loan terms.

        Returns:
            Dictionary mapping term years to MortgageSummary
        """
        results = {}
        original_term = self.property.loan_term_years

        for term in terms:
            self.property.loan_term_years = term
            results[term] = self.calculate_mortgage_summary()

        # Restore original
        self.property.loan_term_years = original_term

        return results

    def calculate_extra_payment_impact(
        self,
        extra_monthly: float
    ) -> dict:
        """
        Calculate impact of making extra monthly payments.

        Returns:
            Dictionary with savings and payoff time reduction
        """
        # Original schedule
        original_schedule = self.generate_amortization_schedule()
        original_interest = sum(e.interest for e in original_schedule)
        original_months = len(original_schedule)

        # Calculate with extra payments
        balance = self.property.loan_amount
        monthly_rate = self.property.mortgage_rate / 12
        base_payment = self.calculate_monthly_pi()

        new_schedule = []
        cumulative_interest = 0.0
        month = 0

        while balance > 0.01:  # Small threshold for floating point
            month += 1
            interest = balance * monthly_rate
            base_principal = base_payment - interest

            # Apply extra payment to principal
            total_principal = base_principal + extra_monthly

            # Don't overpay
            if total_principal > balance:
                total_principal = balance

            balance -= total_principal
            cumulative_interest += interest

            new_schedule.append({
                'month': month,
                'interest': interest,
                'principal': total_principal,
                'balance': balance
            })

        new_interest = cumulative_interest
        new_months = len(new_schedule)

        return {
            'extra_monthly_payment': extra_monthly,
            'original_term_months': original_months,
            'new_term_months': new_months,
            'months_saved': original_months - new_months,
            'years_saved': (original_months - new_months) / 12,
            'original_total_interest': original_interest,
            'new_total_interest': new_interest,
            'interest_saved': original_interest - new_interest,
            'total_extra_paid': extra_monthly * new_months,
            'net_savings': (original_interest - new_interest) - (extra_monthly * new_months)
        }


def calculate_max_home_price(
    monthly_budget: float,
    annual_rate: float,
    term_years: int,
    down_payment_percent: float,
    property_tax_rate: float = 0.0125,
    insurance_annual: float = 1500.0,
    hoa_monthly: float = 0.0,
    include_pmi: bool = True,
    pmi_rate: float = 0.005
) -> float:
    """
    Calculate maximum home price given a monthly budget.

    Args:
        monthly_budget: Maximum monthly housing payment
        annual_rate: Annual mortgage interest rate
        term_years: Loan term in years
        down_payment_percent: Down payment as decimal (e.g., 0.20)
        property_tax_rate: Annual property tax rate
        insurance_annual: Annual homeowners insurance
        hoa_monthly: Monthly HOA fees
        include_pmi: Whether to include PMI in calculation
        pmi_rate: Annual PMI rate if applicable

    Returns:
        Maximum home price
    """
    monthly_rate = annual_rate / 12
    num_payments = term_years * 12
    loan_percent = 1 - down_payment_percent

    # Start with budget minus fixed costs
    available_for_loan = monthly_budget - hoa_monthly - (insurance_annual / 12)

    # Iteratively solve for home price
    # home_price = loan / loan_percent
    # monthly_tax = home_price * property_tax_rate / 12
    # monthly_pmi = loan * pmi_rate / 12 (if applicable)

    # This requires iteration since taxes and PMI depend on home price
    home_price = 100000  # Initial guess

    for _ in range(100):
        loan = home_price * loan_percent

        # Monthly property tax
        monthly_tax = home_price * property_tax_rate / 12

        # Monthly PMI
        monthly_pmi = 0
        if include_pmi and down_payment_percent < 0.20:
            monthly_pmi = loan * pmi_rate / 12

        # Available for P&I
        available_pi = available_for_loan - monthly_tax - monthly_pmi

        if available_pi <= 0:
            home_price *= 0.9
            continue

        # Calculate max loan from available P&I
        if monthly_rate == 0:
            max_loan = available_pi * num_payments
        else:
            max_loan = available_pi * (
                ((1 + monthly_rate) ** num_payments - 1)
                / (monthly_rate * (1 + monthly_rate) ** num_payments)
            )

        new_home_price = max_loan / loan_percent

        if abs(new_home_price - home_price) < 100:
            break

        home_price = new_home_price

    return home_price
