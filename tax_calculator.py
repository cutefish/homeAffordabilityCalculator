"""
Tax calculator for Federal and California taxes.

Handles:
- Federal income tax
- California state income tax
- Federal capital gains tax (short-term and long-term)
- California capital gains (taxed as ordinary income)
- Net Investment Income Tax (NIIT)
- Social Security and Medicare taxes
"""

from dataclasses import dataclass
from config import FilingStatus


# 2024 Federal Income Tax Brackets
FEDERAL_BRACKETS_2024 = {
    FilingStatus.SINGLE: [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (609350, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (23200, 0.10),
        (94300, 0.12),
        (201050, 0.22),
        (383900, 0.24),
        (487450, 0.32),
        (731200, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (365600, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (16550, 0.10),
        (63100, 0.12),
        (100500, 0.22),
        (191950, 0.24),
        (243700, 0.32),
        (609350, 0.35),
        (float('inf'), 0.37),
    ],
}

# 2024 Federal Long-Term Capital Gains Brackets
FEDERAL_LTCG_BRACKETS_2024 = {
    FilingStatus.SINGLE: [
        (47025, 0.0),
        (518900, 0.15),
        (float('inf'), 0.20),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (94050, 0.0),
        (583750, 0.15),
        (float('inf'), 0.20),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (47025, 0.0),
        (291850, 0.15),
        (float('inf'), 0.20),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (63000, 0.0),
        (551350, 0.15),
        (float('inf'), 0.20),
    ],
}

# NIIT thresholds (3.8% on investment income above these thresholds)
NIIT_THRESHOLDS = {
    FilingStatus.SINGLE: 200000,
    FilingStatus.MARRIED_FILING_JOINTLY: 250000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 125000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 200000,
}

# 2024 California Income Tax Brackets
CALIFORNIA_BRACKETS_2024 = {
    FilingStatus.SINGLE: [
        (10412, 0.01),
        (24684, 0.02),
        (38959, 0.04),
        (54081, 0.06),
        (68350, 0.08),
        (349137, 0.093),
        (418961, 0.103),
        (698271, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (20824, 0.01),
        (49368, 0.02),
        (77918, 0.04),
        (108162, 0.06),
        (136700, 0.08),
        (698274, 0.093),
        (837922, 0.103),
        (1396542, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (10412, 0.01),
        (24684, 0.02),
        (38959, 0.04),
        (54081, 0.06),
        (68350, 0.08),
        (349137, 0.093),
        (418961, 0.103),
        (698271, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (20839, 0.01),
        (49371, 0.02),
        (63644, 0.04),
        (78765, 0.06),
        (93037, 0.08),
        (474824, 0.093),
        (569790, 0.103),
        (949649, 0.113),
        (float('inf'), 0.123),
    ],
}

# California Mental Health Services Tax (additional 1% on income over $1M)
CA_MENTAL_HEALTH_THRESHOLD = 1000000
CA_MENTAL_HEALTH_RATE = 0.01

# Social Security and Medicare
SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE_2024 = 168600
MEDICARE_RATE = 0.0145
MEDICARE_ADDITIONAL_RATE = 0.009  # Additional Medicare tax
MEDICARE_ADDITIONAL_THRESHOLD = {
    FilingStatus.SINGLE: 200000,
    FilingStatus.MARRIED_FILING_JOINTLY: 250000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 125000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 200000,
}

# Standard deductions for 2024
STANDARD_DEDUCTION_2024 = {
    FilingStatus.SINGLE: 14600,
    FilingStatus.MARRIED_FILING_JOINTLY: 29200,
    FilingStatus.MARRIED_FILING_SEPARATELY: 14600,
    FilingStatus.HEAD_OF_HOUSEHOLD: 21900,
}

# California standard deduction for 2024
CA_STANDARD_DEDUCTION_2024 = {
    FilingStatus.SINGLE: 5363,
    FilingStatus.MARRIED_FILING_JOINTLY: 10726,
    FilingStatus.MARRIED_FILING_SEPARATELY: 5363,
    FilingStatus.HEAD_OF_HOUSEHOLD: 10726,
}


def calculate_tax_from_brackets(
    taxable_income: float,
    brackets: list[tuple[float, float]]
) -> float:
    """
    Calculate tax using progressive brackets.

    Args:
        taxable_income: The taxable income amount
        brackets: List of (threshold, rate) tuples, sorted by threshold

    Returns:
        Total tax amount
    """
    if taxable_income <= 0:
        return 0.0

    tax = 0.0
    prev_threshold = 0.0

    for threshold, rate in brackets:
        if taxable_income <= prev_threshold:
            break

        taxable_in_bracket = min(taxable_income, threshold) - prev_threshold
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate

        prev_threshold = threshold

    return tax


@dataclass
class TaxBreakdown:
    """Detailed breakdown of taxes."""
    federal_income_tax: float = 0.0
    federal_capital_gains_tax: float = 0.0
    niit: float = 0.0
    state_income_tax: float = 0.0
    state_capital_gains_tax: float = 0.0
    social_security_tax: float = 0.0
    medicare_tax: float = 0.0

    @property
    def total_federal(self) -> float:
        return (
            self.federal_income_tax
            + self.federal_capital_gains_tax
            + self.niit
            + self.social_security_tax
            + self.medicare_tax
        )

    @property
    def total_state(self) -> float:
        return self.state_income_tax + self.state_capital_gains_tax

    @property
    def total_tax(self) -> float:
        return self.total_federal + self.total_state


class TaxCalculator:
    """Calculator for federal and state taxes."""

    def __init__(
        self,
        filing_status: FilingStatus,
        state: str = "CA",
        year: int = 2024
    ):
        self.filing_status = filing_status
        self.state = state
        self.year = year

    def calculate_federal_income_tax(
        self,
        ordinary_income: float,
        use_standard_deduction: bool = True,
        itemized_deductions: float = 0.0
    ) -> float:
        """Calculate federal income tax on ordinary income."""
        deduction = (
            STANDARD_DEDUCTION_2024[self.filing_status]
            if use_standard_deduction
            else itemized_deductions
        )
        taxable_income = max(0, ordinary_income - deduction)

        brackets = FEDERAL_BRACKETS_2024[self.filing_status]
        return calculate_tax_from_brackets(taxable_income, brackets)

    def calculate_federal_capital_gains_tax(
        self,
        ordinary_income: float,
        short_term_gains: float,
        long_term_gains: float,
        use_standard_deduction: bool = True,
        itemized_deductions: float = 0.0
    ) -> tuple[float, float]:
        """
        Calculate federal capital gains tax.

        Returns:
            Tuple of (short_term_tax, long_term_tax)
        """
        deduction = (
            STANDARD_DEDUCTION_2024[self.filing_status]
            if use_standard_deduction
            else itemized_deductions
        )

        # Short-term gains are taxed as ordinary income
        # Calculate marginal rate based on ordinary income
        taxable_ordinary = max(0, ordinary_income - deduction)

        # Tax on ordinary income alone
        base_tax = calculate_tax_from_brackets(
            taxable_ordinary,
            FEDERAL_BRACKETS_2024[self.filing_status]
        )

        # Tax on ordinary income + short-term gains
        tax_with_stcg = calculate_tax_from_brackets(
            taxable_ordinary + short_term_gains,
            FEDERAL_BRACKETS_2024[self.filing_status]
        )

        short_term_tax = tax_with_stcg - base_tax

        # Long-term gains use preferential rates
        # The rate depends on total taxable income (including the gains)
        total_income_for_ltcg = taxable_ordinary + short_term_gains

        # Calculate LTCG tax based on income level
        ltcg_brackets = FEDERAL_LTCG_BRACKETS_2024[self.filing_status]

        # Find the applicable rate(s) for long-term gains
        long_term_tax = 0.0
        remaining_gains = long_term_gains
        income_level = total_income_for_ltcg

        for threshold, rate in ltcg_brackets:
            if remaining_gains <= 0:
                break

            # How much room is there in this bracket?
            room_in_bracket = max(0, threshold - income_level)

            if room_in_bracket > 0:
                gains_at_this_rate = min(remaining_gains, room_in_bracket)
                long_term_tax += gains_at_this_rate * rate
                remaining_gains -= gains_at_this_rate
                income_level += gains_at_this_rate
            else:
                # Income already exceeds this bracket threshold
                continue

        # Any remaining gains are at the highest rate
        if remaining_gains > 0:
            long_term_tax += remaining_gains * ltcg_brackets[-1][1]

        return short_term_tax, long_term_tax

    def calculate_niit(
        self,
        ordinary_income: float,
        investment_income: float
    ) -> float:
        """
        Calculate Net Investment Income Tax (3.8%).

        NIIT applies to the lesser of:
        - Net investment income, OR
        - The amount by which MAGI exceeds the threshold
        """
        threshold = NIIT_THRESHOLDS[self.filing_status]
        magi = ordinary_income + investment_income

        if magi <= threshold:
            return 0.0

        excess_over_threshold = magi - threshold
        niit_base = min(investment_income, excess_over_threshold)

        return niit_base * 0.038

    def calculate_california_income_tax(
        self,
        total_income: float,
        use_standard_deduction: bool = True,
        itemized_deductions: float = 0.0
    ) -> float:
        """
        Calculate California state income tax.

        Note: California taxes capital gains as ordinary income.
        """
        if self.state != "CA":
            return 0.0

        deduction = (
            CA_STANDARD_DEDUCTION_2024[self.filing_status]
            if use_standard_deduction
            else itemized_deductions
        )
        taxable_income = max(0, total_income - deduction)

        # Regular California tax
        brackets = CALIFORNIA_BRACKETS_2024[self.filing_status]
        tax = calculate_tax_from_brackets(taxable_income, brackets)

        # Mental Health Services Tax (additional 1% over $1M)
        if taxable_income > CA_MENTAL_HEALTH_THRESHOLD:
            tax += (taxable_income - CA_MENTAL_HEALTH_THRESHOLD) * CA_MENTAL_HEALTH_RATE

        return tax

    def calculate_payroll_taxes(self, wages: float) -> tuple[float, float]:
        """
        Calculate Social Security and Medicare taxes.

        Returns:
            Tuple of (social_security_tax, medicare_tax)
        """
        # Social Security (capped at wage base)
        ss_wages = min(wages, SOCIAL_SECURITY_WAGE_BASE_2024)
        social_security = ss_wages * SOCIAL_SECURITY_RATE

        # Medicare (no cap, but additional tax above threshold)
        medicare = wages * MEDICARE_RATE
        threshold = MEDICARE_ADDITIONAL_THRESHOLD[self.filing_status]
        if wages > threshold:
            medicare += (wages - threshold) * MEDICARE_ADDITIONAL_RATE

        return social_security, medicare

    def calculate_full_tax_breakdown(
        self,
        wages: float,
        short_term_gains: float = 0.0,
        long_term_gains: float = 0.0,
        other_income: float = 0.0,
        use_standard_deduction: bool = True,
        itemized_deductions: float = 0.0,
        mortgage_interest: float = 0.0,
        property_taxes_paid: float = 0.0
    ) -> TaxBreakdown:
        """
        Calculate complete tax breakdown for a year.

        Args:
            wages: W-2 wages
            short_term_gains: Short-term capital gains
            long_term_gains: Long-term capital gains
            other_income: Other ordinary income
            use_standard_deduction: Whether to use standard deduction
            itemized_deductions: Total itemized deductions if not using standard
            mortgage_interest: Mortgage interest (for itemized deductions)
            property_taxes_paid: Property taxes paid (for SALT deduction, capped)

        Returns:
            TaxBreakdown with all tax components
        """
        ordinary_income = wages + other_income

        # Calculate itemized deductions if provided
        if not use_standard_deduction:
            # SALT deduction capped at $10,000
            salt_deduction = min(property_taxes_paid, 10000)
            itemized = mortgage_interest + salt_deduction + itemized_deductions
        else:
            itemized = 0.0

        # Determine which deduction to use
        standard = STANDARD_DEDUCTION_2024[self.filing_status]
        effective_deduction = max(standard, itemized) if not use_standard_deduction else standard
        use_std = effective_deduction == standard

        # Federal income tax (on ordinary income only)
        federal_income = self.calculate_federal_income_tax(
            ordinary_income=ordinary_income,
            use_standard_deduction=use_std,
            itemized_deductions=itemized
        )

        # Federal capital gains tax
        stcg_tax, ltcg_tax = self.calculate_federal_capital_gains_tax(
            ordinary_income=ordinary_income,
            short_term_gains=short_term_gains,
            long_term_gains=long_term_gains,
            use_standard_deduction=use_std,
            itemized_deductions=itemized
        )

        # NIIT
        investment_income = short_term_gains + long_term_gains
        niit = self.calculate_niit(ordinary_income, investment_income)

        # California tax (all income treated equally)
        total_income = ordinary_income + short_term_gains + long_term_gains
        state_tax = self.calculate_california_income_tax(
            total_income=total_income,
            use_standard_deduction=True  # CA has limited itemized benefit
        )

        # Payroll taxes
        ss_tax, medicare_tax = self.calculate_payroll_taxes(wages)

        return TaxBreakdown(
            federal_income_tax=federal_income,
            federal_capital_gains_tax=stcg_tax + ltcg_tax,
            niit=niit,
            state_income_tax=state_tax,
            state_capital_gains_tax=0.0,  # Included in state_income_tax for CA
            social_security_tax=ss_tax,
            medicare_tax=medicare_tax
        )


def estimate_marginal_tax_rate(
    filing_status: FilingStatus,
    taxable_income: float,
    state: str = "CA"
) -> dict[str, float]:
    """
    Estimate marginal tax rates at a given income level.

    Returns:
        Dictionary with federal, state, and combined marginal rates
    """
    # Find federal marginal rate
    federal_rate = 0.0
    for threshold, rate in FEDERAL_BRACKETS_2024[filing_status]:
        if taxable_income <= threshold:
            federal_rate = rate
            break
        federal_rate = rate

    # Find California marginal rate
    state_rate = 0.0
    if state == "CA":
        for threshold, rate in CALIFORNIA_BRACKETS_2024[filing_status]:
            if taxable_income <= threshold:
                state_rate = rate
                break
            state_rate = rate

        # Add mental health tax if applicable
        if taxable_income > CA_MENTAL_HEALTH_THRESHOLD:
            state_rate += CA_MENTAL_HEALTH_RATE

    return {
        "federal": federal_rate,
        "state": state_rate,
        "combined": federal_rate + state_rate
    }
