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

## Transaktions- og saldorapport

1. In SaxoTrader, download the **Handels- og saldorapport** (PDF) for the same period and put it in `data/`.
2. Run:

   ```sh
   .venv/bin/python -m saxobank.transaction_report
   ```

This writes CSV files to `output/transactions/`, per account:

| File | Contents |
|---|---|
| `trades.csv` | Every booking: trades, dividends, deposits, fees, interest and corporate actions |
| `closed_positions.csv` | Closed positions with open/close dates, prices and realized gain/loss |
| `bookings.csv` | Bookings summed by product and type |
| `positions.csv` | Current positions per lot, with ISIN and market value |

Account ids are not written out. Accounts are named by type (e.g. Aktiesparekonto) or numbered.

## Own return calculations

```sh
.venv/bin/python -m saxobank.returns
```

Uses both reports and writes to `output/returns/`:

| File | Contents |
|---|---|
| `instrument_returns.csv` | Per account and instrument: invested, sold, dividends, costs, market value, gain/loss, return on invested amount and annual money-weighted return (XIRR) |
| `account_returns.csv` | Per account and in total: deposits, withdrawals, value today, gain/loss and annual money-weighted return |

The booked amounts in the report already include costs, so the gain on an instrument is its market value plus everything booked on it. The account totals match the portfolio report exactly. Per instrument, a few papers differ from Saxo's own figure, because Saxo counts dividends (gross vs. after tax) and corporate actions (mergers, spin-offs) differently per instrument.

## Tests

```sh
.venv/bin/python -m pytest
```
