# Claude Code Rules

Guidelines for Claude when working on this codebase.

## Code Quality

### Imports
- **Clean up unused imports** - Remove any imports that are not used in the file
- Keep imports organized: standard library first, then third-party, then local modules
- Use explicit imports rather than wildcard imports (`from module import *`)

### General
- Remove dead code and unused classes/functions after refactoring
- Keep the codebase minimal - don't leave superseded files around
- Test changes before committing

## Project Structure

This is a unified financial simulation engine for home affordability analysis.

### Core Files
- `config.py` - Core enums (FilingStatus, RSUTerm, InvestmentType)
- `tax_calculator.py` - Federal and California tax calculations
- `simulation_engine.py` - Unified multi-year simulation engine
- `run_simulation.py` - Example usage and demonstration

### Running the Simulation
```bash
python3 run_simulation.py
```

## Financial Concepts

### Key Inputs
- Income schedule (annual projections)
- RSU holdings and future vesting schedule
- RSU selling strategy (immediate, at purchase, long-term, hold)
- Investment accounts
- House purchase plan (price, down payment, rate)
- Market assumptions (stock prices, appreciation rates)

### Key Outputs
- Monthly cash flow projections
- Net worth trajectory
- Breakeven analysis (buying vs renting)
