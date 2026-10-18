"""Our own return calculations from the transaction report.

Usage:
    python -m saxobank.returns

Reads the newest TransactionBalance_*.pdf and Portfolio_*.pdf in data/ and
writes output/returns/instrument_returns.csv and account_returns.csv.
Only row counts and checks are printed.

Every booked amount in the transaction report already includes costs, so
the gain on an instrument is simply its market value today plus the sum of
everything booked on it (purchases negative, sales and dividends positive).
Corporate actions (mergers, spin-offs, name changes) can move value from
one instrument name to another; the totals are still right.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from saxobank.portfolio_report import parse_portfolio_report
from saxobank.transaction_report import parse_transaction_report

BUY = {"Købt"}
SELL = {"Solgt"}
DIVIDEND = {"Kontantudbytte", "Udbytte", "Udlodning"}
DEPOSIT = {"Indbetaling"}
WITHDRAWAL = {"Udbetaling"}
REPORT_DATES = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.pdf$")


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Annual money-weighted return in %, or None if it cannot be found.

    Flows are from the investor's side: money put in is negative, money
    taken out (and today's value) is positive.
    """
    flows = [(d, a) for d, a in flows if a]
    if len(flows) < 2 or not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    start = min(d for d, _ in flows)
    years = [((d - start).days / 365.25, a) for d, a in flows]
    if max(t for t, _ in years) < 1 / 365.25:
        return None

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** t for t, a in years)

    lo, hi = -0.9999, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2 * 100


def instrument_returns(trades: pd.DataFrame, positions: pd.DataFrame, end: date) -> pd.DataFrame:
    trades = trades[~trades["is_total"] & (trades["product"] != "Kontanter") & trades["instrument"].notna()]
    held = positions[~positions["is_total"]]
    market_value = held.groupby(["account", "instrument"])["market_value"].sum()
    isin = held.groupby(["account", "instrument"])["isin"].first()
    rows = []
    for (account, instrument), t in trades.groupby(["account", "instrument"]):
        booked = t["booked_amount"].fillna(0)
        kind = t["event_type"]
        mv = market_value.get((account, instrument), 0.0)
        invested = -booked[kind.isin(BUY)].sum()
        gain = mv + booked.sum()
        flows = [(d, a) for d, a in zip(t["value_date"], booked)] + [(end, mv)]
        rows.append({
            "account": account,
            "instrument": instrument,
            "isin": isin.get((account, instrument)),
            "product": t["product"].iloc[0],
            "first_buy": t.loc[kind.isin(BUY), "trade_date"].min(),
            "status": "åben" if mv else "lukket",
            "invested": invested,
            "sold": booked[kind.isin(SELL)].sum(),
            "dividends": booked[kind.isin(DIVIDEND)].sum(),
            "other": booked[~kind.isin(BUY | SELL | DIVIDEND)].sum(),
            "costs": -t["booked_costs"].fillna(0).sum(),
            "realized_gain_loss": t["realized_gain_loss"].fillna(0).sum(),
            "market_value": mv,
            "gain_loss": gain,
            "return_pct": gain / invested * 100 if invested > 0 else None,
            "annual_return_pct": xirr(flows),
        })
    return pd.DataFrame(rows).sort_values(["account", "gain_loss"], ascending=[True, False])


def account_returns(trades: pd.DataFrame, positions: pd.DataFrame, bookings: pd.DataFrame, end: date) -> pd.DataFrame:
    """Net deposits, value today and returns per account and in total.

    Cash today is the bookings total, as every account starts at zero in
    the report period."""
    trades = trades[~trades["is_total"]]
    cash = bookings[bookings["is_total"]].set_index("account")["total"]
    held = positions[~positions["is_total"]].groupby("account")["market_value"].sum()
    rows = []
    for account in [*sorted(trades["account"].unique()), "I alt"]:
        t = trades if account == "I alt" else trades[trades["account"] == account]
        kind = t["event_type"]
        deposits = t.loc[kind.isin(DEPOSIT), "booked_amount"].sum()
        withdrawals = -t.loc[kind.isin(WITHDRAWAL), "booked_amount"].sum()
        value = (cash.sum() + held.sum()) if account == "I alt" else cash.get(account, 0.0) + held.get(account, 0.0)
        external = t[kind.isin(DEPOSIT | WITHDRAWAL)]
        flows = [(d, -a) for d, a in zip(external["value_date"], external["booked_amount"])] + [(end, value)]
        net = deposits - withdrawals
        rows.append({
            "account": account,
            "deposits": deposits,
            "withdrawals": withdrawals,
            "net_deposits": net,
            "cash": cash.sum() if account == "I alt" else cash.get(account, 0.0),
            "positions": held.sum() if account == "I alt" else held.get(account, 0.0),
            "value": value,
            "gain_loss": value - net,
            "return_on_net_deposits_pct": (value - net) / net * 100 if net > 0 else None,
            "annual_return_pct": xirr(flows),
        })
    return pd.DataFrame(rows)


def _close(a, b, tol=1.0) -> bool:
    return pd.notna(a) and pd.notna(b) and abs(a - b) <= tol


def checks(accounts: pd.DataFrame, portfolio: dict[str, pd.DataFrame]) -> list[tuple[str, bool]]:
    s = portfolio["summary"].iloc[0]
    total = accounts[accounts["account"] == "I alt"].iloc[0]
    # Upcoming dividends and interest are in Saxo's account value but not yet booked.
    unbooked = portfolio["holdings_overview"].set_index("product")["market_value"].get("Akkumulerede ikke-bogførte beløb", 0.0)
    return [
        ("Konti: værdi i alt + ikke-bogførte beløb = slutværdi i porteføljerapporten",
         _close(total["value"] + unbooked, s.end_value)),
        ("Konti: nettoindbetalinger i alt = nettoindbetalinger i porteføljerapporten",
         _close(total["net_deposits"], s.net_deposits)),
    ]


def compare_with_saxo(instruments: pd.DataFrame, portfolio: dict[str, pd.DataFrame]) -> tuple[int, int]:
    """How many instruments have the same gain/loss as Saxo's own figure
    (within 0.5 %). Not a check: Saxo counts some dividends and corporate
    actions differently per instrument, so a few papers differ."""
    saxo = portfolio["gain_by_instrument"]
    saxo = saxo[~saxo["is_total"]].groupby("instrument")["gain_loss"].sum()
    ours = instruments.groupby("instrument")["gain_loss"].sum()
    common = ours.index.intersection(saxo.index)
    matching = sum(_close(ours[i], saxo[i], max(1.0, abs(saxo[i]) * 0.005)) for i in common)
    return matching, len(common)


def _newest(pattern: str) -> Path:
    candidates = sorted(Path("data").glob(pattern), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise SystemExit(f"No {pattern} found in data/")
    return candidates[-1]


def main(argv: list[str]) -> int:
    transaction_path = _newest("TransactionBalance_*.pdf")
    m = REPORT_DATES.search(transaction_path.name)
    end = date.fromisoformat(m.group(2)) if m else date.today()
    tables = parse_transaction_report(transaction_path)
    portfolio = parse_portfolio_report(_newest("Portfolio_*.pdf"))

    instruments = instrument_returns(tables["trades"], tables["positions"], end)
    accounts = account_returns(tables["trades"], tables["positions"], tables["bookings"], end)
    out = Path("output/returns")
    out.mkdir(parents=True, exist_ok=True)
    for name, df in (("instrument_returns", instruments), ("account_returns", accounts)):
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"{name:20s} {len(df):4d} rows -> {out / (name + '.csv')}")
    print()
    results = checks(accounts, portfolio)
    for description, passed in results:
        print(f"[{'OK' if passed else 'FEJL'}] {description}")
    matching, common = compare_with_saxo(instruments, portfolio)
    print(f"[INFO] Gevinst/tab pr. papir er det samme som Saxos for {matching} af {common} papirer (±0,5 %)")
    return 0 if all(passed for _, passed in results) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
