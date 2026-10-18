# saxobankData

Analyse a Saxo Bank portfolio from reports exported manually from SaxoTrader. There is no connection to Saxo: no login, no API keys, no network calls.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Porteføljerapport

1. In SaxoTrader, download the **Portefølje Rapport** (PDF) for the whole period and put it in `data/`.
2. Run:

   ```sh
   .venv/bin/python -m saxobank.portfolio_report
   ```

This writes CSV files to `output/portfolio/`:

| File | Contents |
|---|---|
| `summary.csv` | Start and end value, net deposits, total gain/loss and return |
| `account_value.csv` | Cash, unbooked amounts, positions and account value by date |
| `period_returns.csv` | Time-weighted return, gain/loss and costs per period |
| `gain_by_product.csv` | Income, costs and gain/loss per product type |
| `gain_by_instrument.csv` | Income, costs, gain/loss and return per instrument |
| `holdings_overview.csv` | Market value and weight per product |
| `positions.csv` | Every current position with ISIN, quantity, prices and market value |

The script only prints row counts and checks against the report's own totals, never the data itself. `data/` and `output/` are in `.gitignore`.

## Tests

```sh
.venv/bin/python -m pytest
```
