"""
Configuration Loader for Home Affordability Simulator

This module loads simulation inputs from JSON configuration files,
with support for loading RSU holdings from brokerage CSV exports.

Supported CSV formats:
- Fidelity RSU export format
- Generic CSV with required columns

Usage:
    from config_loader import load_config
    inputs = load_config("my_config.json")
"""

import json
import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from simulation_engine import (
    SimulationInputs,
    IncomeProfile,
    RSULot,
    FutureRSUVest,
    RSUSellRule,
    RSUSellStrategy,
    InvestmentAccount,
    DebtObligation,
    HousePurchasePlan,
    MarketAssumptions,
)
from config import FilingStatus, InvestmentType


def parse_date(date_str: str) -> date:
    """Parse a date string in various formats."""
    if not date_str:
        raise ValueError("Empty date string")

    # Try ISO format first (YYYY-MM-DD)
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Try Mon-DD-YYYY format (e.g., Sep-29-2025)
    try:
        return datetime.strptime(date_str, "%b-%d-%Y").date()
    except ValueError:
        pass

    # Try MM/DD/YYYY format
    try:
        return datetime.strptime(date_str, "%m/%d/%Y").date()
    except ValueError:
        pass

    raise ValueError(f"Unable to parse date: {date_str}")


def parse_money(value: str | float | int) -> float:
    """Parse a money value, handling currency symbols and formatting."""
    if isinstance(value, (int, float)):
        return float(value)

    # Remove currency symbols, commas, and whitespace
    cleaned = re.sub(r'[$,\s]', '', str(value))

    # Handle parentheses for negative numbers
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]

    return float(cleaned)


def parse_percentage(value: str | float) -> float:
    """Parse a percentage value."""
    if isinstance(value, float):
        return value if value <= 1 else value / 100

    cleaned = str(value).replace('%', '').strip()
    result = float(cleaned)

    # If value > 1, assume it's a percentage (e.g., 6.75 -> 0.0675)
    if result > 1:
        result = result / 100

    return result


def load_rsu_csv(csv_path: str, base_dir: Path = None) -> list[RSULot]:
    """
    Load RSU holdings from a brokerage CSV export.

    Supports Fidelity-style exports with columns:
    - Acquired: Vest date (e.g., "Sep-29-2025")
    - Quantity: Number of shares
    - Average cost basis: Cost basis per share
    - Grant Date: Original grant date (used for lot ID)

    Also supports generic format with columns:
    - vest_date or Acquired
    - shares or Quantity
    - cost_basis_per_share or Average cost basis
    - lot_id (optional)
    """
    if base_dir:
        csv_path = base_dir / csv_path
    else:
        csv_path = Path(csv_path)

    lots = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        # Try to detect delimiter
        sample = f.read(2048)
        f.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',\t')
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(f, dialect=dialect)

        # Normalize column names (lowercase, strip whitespace)
        if reader.fieldnames:
            column_map = {name.lower().strip(): name for name in reader.fieldnames}
        else:
            raise ValueError(f"No headers found in CSV: {csv_path}")

        for i, row in enumerate(reader):
            # Skip empty rows
            if not any(row.values()):
                continue

            # Extract vest date
            vest_date = None
            for key in ['acquired', 'vest_date', 'vest date', 'vested']:
                if key in column_map:
                    try:
                        vest_date = parse_date(row[column_map[key]])
                        break
                    except (ValueError, KeyError):
                        continue

            if not vest_date:
                raise ValueError(f"Row {i+1}: Could not find or parse vest date")

            # Extract shares
            shares = None
            for key in ['quantity', 'shares', 'share count', 'qty']:
                if key in column_map:
                    try:
                        shares = int(float(row[column_map[key]]))
                        break
                    except (ValueError, KeyError):
                        continue

            if shares is None:
                raise ValueError(f"Row {i+1}: Could not find or parse shares")

            # Extract cost basis per share
            cost_basis = None
            for key in ['average cost basis', 'cost_basis_per_share', 'cost basis', 'avg cost']:
                if key in column_map:
                    try:
                        cost_basis = parse_money(row[column_map[key]])
                        break
                    except (ValueError, KeyError):
                        continue

            if cost_basis is None:
                raise ValueError(f"Row {i+1}: Could not find or parse cost basis")

            # Extract lot ID (optional)
            lot_id = None
            for key in ['lot_id', 'lot id', 'grant date']:
                if key in column_map:
                    lot_id = row[column_map[key]]
                    break

            if not lot_id:
                lot_id = f"LOT-{vest_date.isoformat()}-{i+1}"
            else:
                # If using grant date, make it more descriptive
                lot_id = f"VEST-{vest_date.strftime('%Y%m%d')}-{lot_id}"

            lots.append(RSULot(
                lot_id=lot_id,
                shares=shares,
                cost_basis_per_share=cost_basis,
                vest_date=vest_date
            ))

    return lots


def load_config(config_path: str) -> SimulationInputs:
    """
    Load simulation inputs from a JSON configuration file.

    Args:
        config_path: Path to the JSON configuration file

    Returns:
        SimulationInputs object ready for simulation
    """
    config_path = Path(config_path)
    base_dir = config_path.parent

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Parse filing status
    filing_status_str = config.get('filing_status', 'SINGLE')
    filing_status = FilingStatus[filing_status_str.upper().replace(' ', '_')]

    # Parse dates
    start_date = parse_date(config.get('start_date', date.today().isoformat()))

    # Parse income schedule
    income_schedule = []
    for inc in config.get('income_schedule', []):
        income_schedule.append(IncomeProfile(
            year=inc['year'],
            base_salary=parse_money(inc['base_salary']),
            bonus=parse_money(inc.get('bonus', 0))
        ))

    # Parse RSU holdings (inline or from CSV file)
    rsu_holdings = []
    rsu_config = config.get('rsu_holdings', [])

    if isinstance(rsu_config, str):
        # It's a file reference
        rsu_holdings = load_rsu_csv(rsu_config, base_dir)
    elif isinstance(rsu_config, dict) and 'file' in rsu_config:
        # It's a file reference object
        rsu_holdings = load_rsu_csv(rsu_config['file'], base_dir)
    else:
        # It's inline data
        for lot in rsu_config:
            rsu_holdings.append(RSULot(
                lot_id=lot['lot_id'],
                shares=int(lot['shares']),
                cost_basis_per_share=parse_money(lot['cost_basis_per_share']),
                vest_date=parse_date(lot['vest_date'])
            ))

    # Parse future RSU vests
    future_rsu_vests = []
    for vest in config.get('future_rsu_vests', []):
        future_rsu_vests.append(FutureRSUVest(
            vest_id=vest['vest_id'],
            shares=int(vest['shares']),
            vest_date=parse_date(vest['vest_date'])
        ))

    # Parse RSU sell rules
    rsu_sell_rules = []
    strategy_map = {
        'SELL_IMMEDIATELY': RSUSellStrategy.SELL_IMMEDIATELY,
        'SELL_AT_PURCHASE': RSUSellStrategy.SELL_AT_PURCHASE,
        'SELL_LONG_TERM': RSUSellStrategy.SELL_LONG_TERM,
        'HOLD': RSUSellStrategy.HOLD,
        'CUSTOM': RSUSellStrategy.CUSTOM,
    }

    for rule in config.get('rsu_sell_rules', []):
        strategy = strategy_map[rule['strategy'].upper()]
        sell_date = None
        if 'sell_date' in rule:
            sell_date = parse_date(rule['sell_date'])

        rsu_sell_rules.append(RSUSellRule(
            lot_id=rule['lot_id'],
            strategy=strategy,
            sell_date=sell_date
        ))

    # Parse investments
    investments = []
    type_map = {
        'MONEY_MARKET': InvestmentType.MONEY_MARKET,
        'STOCKS': InvestmentType.STOCKS,
        'BONDS': InvestmentType.BONDS,
        'ETFS': InvestmentType.ETFS,
        'CD': InvestmentType.CD,
        'MANAGED_ACCOUNT': InvestmentType.MANAGED_ACCOUNT,
    }

    for inv in config.get('investments', []):
        investments.append(InvestmentAccount(
            name=inv['name'],
            account_type=type_map[inv['account_type'].upper()],
            balance=parse_money(inv['balance']),
            cost_basis=parse_money(inv.get('cost_basis', inv['balance'])),
            annual_return=parse_percentage(inv.get('annual_return', 0.05)),
            is_liquid=inv.get('is_liquid', True)
        ))

    # Parse debts
    debts = []
    for debt in config.get('debts', []):
        debts.append(DebtObligation(
            name=debt['name'],
            monthly_payment=parse_money(debt['monthly_payment']),
            remaining_balance=parse_money(debt['remaining_balance']),
            interest_rate=parse_percentage(debt.get('interest_rate', 0))
        ))

    # Parse house plan
    house_plan = None
    if 'house_plan' in config:
        hp = config['house_plan']
        house_plan = HousePurchasePlan(
            purchase_date=parse_date(hp['purchase_date']),
            home_price=parse_money(hp['home_price']),
            down_payment_percent=parse_percentage(hp['down_payment_percent']),
            mortgage_rate=parse_percentage(hp['mortgage_rate']),
            loan_term_years=int(hp.get('loan_term_years', 30)),
            property_tax_rate=parse_percentage(hp.get('property_tax_rate', 0.0125)),
            hoa_monthly=parse_money(hp.get('hoa_monthly', 0)),
            homeowners_insurance_annual=parse_money(hp.get('homeowners_insurance_annual', 1500)),
            maintenance_rate=parse_percentage(hp.get('maintenance_rate', 0.01))
        )

    # Parse market assumptions
    market = None
    if 'market' in config:
        m = config['market']
        stock_prices = {}
        for date_str, price in m.get('stock_prices', {}).items():
            stock_prices[parse_date(date_str)] = parse_money(price)

        market = MarketAssumptions(
            current_stock_price=parse_money(m.get('current_stock_price', 100)),
            stock_prices=stock_prices,  # Empty dict is fine, don't use None
            stock_annual_growth=parse_percentage(m.get('stock_annual_growth', 0.08)),
            home_appreciation_rate=parse_percentage(m.get('home_appreciation_rate', 0.03)),
            rent_increase_rate=parse_percentage(m.get('rent_increase_rate', 0.04)),
            investment_return_rate=parse_percentage(m.get('investment_return_rate', 0.07))
        )

    return SimulationInputs(
        filing_status=filing_status,
        state=config.get('state', 'CA'),
        start_date=start_date,
        initial_cash=parse_money(config.get('initial_cash', 0)),
        income_schedule=income_schedule or None,
        rsu_holdings=rsu_holdings or None,
        future_rsu_vests=future_rsu_vests or None,
        rsu_sell_rules=rsu_sell_rules or None,
        stock_symbol=config.get('stock_symbol', 'STOCK'),
        investments=investments or None,
        debts=debts or [],  # Empty list, not None - simulation iterates over this
        house_plan=house_plan,
        comparable_rent=parse_money(config.get('comparable_rent', 3000)),
        monthly_living_expenses=parse_money(config.get('monthly_living_expenses', 3000)),
        market=market,
        simulation_years=int(config.get('simulation_years', 10))
    )


def create_template_config() -> dict[str, Any]:
    """
    Create a template configuration dictionary.

    Returns:
        Dictionary that can be saved as JSON template
    """
    return {
        "_comment": "Home Affordability Simulation Configuration",
        "_instructions": [
            "Edit this file with your personal financial information.",
            "All money values can include $ and commas (e.g., '$100,000').",
            "Percentages can be decimals (0.0675) or with % sign (6.75%).",
            "Dates should be in YYYY-MM-DD format.",
            "For RSU holdings, you can specify a CSV file path instead of inline data."
        ],

        "filing_status": "SINGLE",
        "state": "CA",
        "start_date": "2025-01-01",
        "initial_cash": 50000,
        "comparable_rent": 3500,
        "monthly_living_expenses": 4000,
        "simulation_years": 10,
        "stock_symbol": "ACME",

        "income_schedule": [
            {"year": 2025, "base_salary": 200000, "bonus": 20000},
            {"year": 2026, "base_salary": 210000, "bonus": 25000},
            {"year": 2027, "base_salary": 220000, "bonus": 30000}
        ],

        "rsu_holdings": {
            "_comment": "Use 'file' to load from CSV, or replace with array of lot objects",
            "file": "rsu_holdings.csv"
        },

        "future_rsu_vests": [
            {"vest_id": "VEST-2025-Q1", "shares": 100, "vest_date": "2025-03-15"},
            {"vest_id": "VEST-2025-Q3", "shares": 100, "vest_date": "2025-09-15"}
        ],

        "rsu_sell_rules": [
            {"lot_id": "all", "strategy": "SELL_IMMEDIATELY"}
        ],

        "investments": [
            {
                "name": "High-Yield Savings",
                "account_type": "MONEY_MARKET",
                "balance": 50000,
                "cost_basis": 50000,
                "annual_return": "4.5%",
                "is_liquid": True,
                "_comment": "Types: MONEY_MARKET, STOCKS, BONDS, ETFS, CD, MANAGED_ACCOUNT"
            },
            {
                "name": "Brokerage Account",
                "account_type": "ETFS",
                "balance": 100000,
                "cost_basis": 80000,
                "annual_return": "8%",
                "is_liquid": True
            }
        ],

        "debts": [
            {
                "name": "Car Loan",
                "monthly_payment": 450,
                "remaining_balance": 15000,
                "interest_rate": "5%"
            }
        ],

        "house_plan": {
            "purchase_date": "2025-06-01",
            "home_price": 1000000,
            "down_payment_percent": "20%",
            "mortgage_rate": "6.75%",
            "loan_term_years": 30,
            "property_tax_rate": "1.25%",
            "hoa_monthly": 400,
            "homeowners_insurance_annual": 2000,
            "maintenance_rate": "1%"
        },

        "market": {
            "current_stock_price": 150,
            "stock_prices": {
                "2025-01-01": 150,
                "2025-06-01": 155,
                "2026-01-01": 165
            },
            "stock_annual_growth": "8%",
            "home_appreciation_rate": "3%",
            "rent_increase_rate": "4%",
            "investment_return_rate": "7%"
        }
    }


if __name__ == "__main__":
    # Generate template config
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--template":
        template = create_template_config()
        print(json.dumps(template, indent=2))
    else:
        print("Usage: python config_loader.py --template > config_template.json")
        print("\nThis will generate a template configuration file.")
