"""
Core enums for the Home Affordability Calculator.
"""

from enum import Enum


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
