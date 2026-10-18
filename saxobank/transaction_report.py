"""Parse Saxo's Transaktions- og saldorapport (TransactionBalance_*.pdf).

Usage:
    python -m saxobank.transaction_report [path/to/TransactionBalance_....pdf]

Without a path, the newest TransactionBalance_*.pdf in data/ is used. Trades,
closed positions, bookings and current positions are written per account to
output/transactions/. Only row counts and consistency checks are printed.
Account ids are never written out: accounts are named by their type
(e.g. Aktiesparekonto) or numbered in the order they appear.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

from saxobank.pdf_layout import (
    Field,
    Word,
    group_lines,
    page_words,
    parse_date,
    parse_number,
    is_unclosed,
    read_anchored_table,
    rejoin_split_cells,
)

FOOTER_TOP = 540.0
TITLE = re.compile(
    r"^(?P<section>.+?)\s+[-–]\s+(?P<name>[^(]*?)\s*\((?P<id>[^)]+)\),\s*(?P<currency>[A-Z]{3})$"
)
ISIN = re.compile(r"\(ISIN:\s*([A-Z]{2}[A-Z0-9]{9}\d)\)")

TRADE_FIELDS = [
    Field("trade_date", "Handelsdato", "left"),
    Field("value_date", "Valørdato", "centre"),
    Field("trade_id", "Handels-id", "centre"),
    Field("product", "Produkt", "centre"),
    Field("instrument", "Instrument", "centre"),
    Field("currency", "Instrumentval", "centre"),
    Field("event", "Eventtype", "centre"),
    Field("open_close", "Åben/luk", "centre"),
    Field("quantity", "Antal", "number"),
    Field("price", "Kurs", "number"),
    Field("fx_rate", "Omregningssats", "number_centre"),
    Field("realized_gain_loss", "Realiseret", "number"),
    Field("booked_amount", "Bogført beløb", "number"),
    Field("booked_costs", "Bogførte", "number_centre"),
    Field("total_costs", "Samlede", "number"),
]
CLOSED_FIELDS = [
    Field("instrument", "Instrument", "left"),
    Field("position_id", "Id for lukket", "centre"),
    Field("close_type", "Lukketype", "centre"),
    Field("open_date", "Åbningsdato", "centre"),
    Field("close_date", "Lukkedato", "centre"),
    Field("quantity", "Antal", "number"),
    Field("open_price", "Åbningskurs", "number"),
    Field("close_price", "Lukkekurs", "number"),
    Field("booked_open_amount", "Bogført åbningsbeløb", "number"),
    Field("booked_close_amount", "Bogført lukkebeløb", "number"),
    Field("realized_gain_loss", "Realiseret", "number"),
]
BOOKING_FIELDS = [
    Field("product", "Produkt", "left"),
    Field("type", "Type", "left"),
    Field("debit", "Debet", "number"),
    Field("credit", "Kredit", "number"),
    Field("total", "I alt", "number"),
]
POSITION_FIELDS = [
    Field("instrument", "Instrument", "left"),
    Field("symbol", "Symbol", "centre"),
    Field("position_id", "Positions-ID", "centre"),
    Field("currency", "Instrumentvalut", "centre"),
    Field("open_date", "Åbningsdato", "centre"),
    Field("quantity", "Antal", "number"),
    Field("fx_rate", "Omregningssats", "number"),
    Field("open_price", "Åbningskurs", "number"),
    Field("price", "Pris", "number"),
    Field("price_change_pct", "Procentvis", "number"),
    Field("gain_loss", "Gevinst/tab", "number"),
    Field("market_value", "Markedsværdi", "number"),
]


def _dated(field):
    def is_anchor(cells: dict[str, list[Word]]) -> bool:
        text = " ".join(w.text for w in cells.get(field, []))
        is_total = any(" ".join(w.text for w in ws).startswith("I alt") for ws in cells.values())
        return parse_date(text) is not None or is_total
    return is_anchor


def _any_amount(cells: dict[str, list[Word]]) -> bool:
    return any(parse_number(w.text) is not None for f in ("debit", "credit", "total") for w in cells.get(f, []))


# name: (header words that identify the table, fields, anchor test, attach distance).
# Long instrument names wrap over up to five lines centred on the row, so
# their outer lines can sit about 24 points from the row's anchor line.
TABLES = {
    "trades": ({"Handelsdato", "Valørdato", "Eventtype"}, TRADE_FIELDS, _dated("trade_date"), 24.0),
    "closed_positions": ({"Lukketype", "Lukkedato"}, CLOSED_FIELDS, _dated("close_date"), 24.0),
    "bookings": ({"Produkt", "Type", "Debet", "Kredit"}, BOOKING_FIELDS, _any_amount, 8.0),
    "positions": ({"Positions-ID", "Åbningskurs"}, POSITION_FIELDS, _dated("open_date"), 24.0),
}
NUMBER_COLUMNS = {
    name: [f.name for f in fields if f.kind.startswith("number")]
    for name, (_, fields, _, _) in TABLES.items()
}
DATE_COLUMNS = ["trade_date", "value_date", "open_date", "close_date"]


def _page_account(lines: list[list[Word]], accounts: dict[str, str]) -> str | None:
    """The account a page belongs to, from its title. The bookings title is
    split over two lines. The account id is only used as a lookup key."""
    if not lines:
        return None
    title = " ".join(w.text for w in lines[0])
    if "(" not in title and len(lines) > 1:
        title += " " + " ".join(w.text for w in lines[1])
    m = TITLE.match(title)
    if not m:
        return None
    if m["id"] not in accounts:
        accounts[m["id"]] = m["name"] or f"Konto {len(accounts) + 1}"
    return accounts[m["id"]]


def _header_band(lines: list[list[Word]], i: int) -> list[int]:
    """The header line and the header lines stacked just above and below it.
    Stacked header lines never start in the left margin; a line that does is
    the title of the table (like 'Aktier'), not part of the header."""
    top = lines[i][0].top
    return [
        j for j, l in enumerate(lines)
        if j == i or (abs(l[0].top - top) <= 15 and l[0].x0 >= 100)
    ]


def _table_blocks(lines: list[list[Word]]):
    """Yield (table name, header band lines, body lines, line before the band)."""
    headers = []
    for i, line in enumerate(lines):
        texts = {w.text for w in line}
        for name, (needed, *_rest) in TABLES.items():
            if needed <= texts:
                headers.append((i, name))
    bands = [_header_band(lines, i) for i, _ in headers]
    for n, ((_, name), band) in enumerate(zip(headers, bands)):
        end = min(bands[n + 1]) if n + 1 < len(bands) else len(lines)
        before = lines[min(band) - 1] if min(band) > 0 else []
        yield name, [lines[j] for j in band], lines[max(band) + 1:end], before


def parse_transaction_report(path: Path) -> dict[str, pd.DataFrame]:
    accounts: dict[str, str] = {}
    rows: dict[str, list[dict]] = {name: [] for name in TABLES}
    with pdfplumber.open(path) as pdf:
        # Page 1 only holds name and address, so it is never read.
        for page in pdf.pages[1:]:
            lines = group_lines(page_words(page, top_max=FOOTER_TOP))
            account = _page_account(lines, accounts)
            for name, band, body, before in _table_blocks(lines):
                _, fields, is_anchor, distance = TABLES[name]
                group = " ".join(w.text for w in before)
                table_rows, leading = read_anchored_table(band, body, fields, is_anchor, distance)
                # The end of an instrument name cut by the page break.
                previous = rows[name][-1] if rows[name] else None
                if previous and leading.get("instrument") and is_unclosed(previous.get("instrument", "")):
                    previous["instrument"] += " " + leading["instrument"]
                for row in table_rows:
                    row = {"account": account, **row}
                    if name == "positions":
                        row["product_group"] = group
                    rows[name].append(row)

    tables = {}
    for name, fields in ((n, t[1]) for n, t in TABLES.items()):
        if any(f.name == "instrument" for f in fields):
            rejoin_split_cells(rows[name], "instrument")
        columns = ["account"] + [f.name for f in fields] + (["product_group"] if name == "positions" else [])
        df = pd.DataFrame(rows[name], columns=columns)
        first = df[fields[0].name].fillna("")
        df["is_total"] = first.str.startswith("I alt")
        df.loc[df["is_total"], fields[0].name] = "I alt"
        for c in NUMBER_COLUMNS[name]:
            df[c] = df[c].map(parse_number)
        for c in DATE_COLUMNS:
            if c in df:
                df[c] = df[c].map(lambda v: parse_date(v) if isinstance(v, str) else None)
        if "instrument" in df:
            df["isin"] = df["instrument"].str.extract(ISIN, expand=False)
            df["instrument"] = df["instrument"].str.replace(ISIN, "", regex=True).str.strip()
            # A trailing '*' marks an instrument that is lent out (værdipapirudlån).
            df["lent_out"] = df["instrument"].str.endswith("*").fillna(False)
            df["instrument"] = df["instrument"].str.rstrip("* ")
        tables[name] = df

    trades = tables["trades"]
    # The product column is narrow, so names wrap mid-word: 'Investeringsf' 'oreninger'.
    trades["product"] = trades["product"].str.replace(" ", "")
    # 'Købt 10 @ 123,45 DKK' -> 'Købt'. The rest of the text holds quantity and price.
    trades["event_type"] = trades["event"].fillna("").str.split().str[0]
    return tables


def checks(tables: dict[str, pd.DataFrame]) -> list[tuple[str, bool]]:
    """Consistency checks against the report's own totals. Returns
    (description, passed) pairs, without any amounts."""
    def close(a, b, tol=1.0):
        return pd.notna(a) and pd.notna(b) and abs(a - b) <= tol

    def sums_to_total(df, column):
        ok = True
        for _, rows in df.groupby("account"):
            total = rows[rows["is_total"]]
            ok &= len(total) == 1 and close(rows[~rows["is_total"]][column].sum(), total[column].iloc[0])
        return bool(ok)

    tr, cl, bk, ps = (tables[n] for n in ("trades", "closed_positions", "bookings", "positions"))
    real = tr[~tr["is_total"]]
    result = [
        ("Handler: alle rækker har handelsdato og valørdato",
         bool(real["trade_date"].notna().all() and real["value_date"].notna().all())),
        ("Handler: alle rækker har et bogført beløb", bool(real["booked_amount"].notna().all())),
        ("Handler: bogført beløb summerer til I alt pr. konto", sums_to_total(tr, "booked_amount")),
        ("Handler: bogførte omkostninger summerer til I alt pr. konto", sums_to_total(tr, "booked_costs")),
        ("Handler: realiseret gevinst/tab summerer til I alt pr. konto", sums_to_total(tr, "realized_gain_loss")),
        ("Lukkede positioner: realiseret gevinst/tab summerer til I alt pr. konto",
         sums_to_total(cl, "realized_gain_loss")),
        ("Bogføringer: rækker summerer til I alt pr. konto", sums_to_total(bk, "total")),
        # The booked amount of a trade already includes its costs.
        ("Bogføringer: I alt = handlernes bogført beløb pr. konto",
         all(close(
             bk[bk["is_total"] & (bk["account"] == a)]["total"].sum(),
             tr[tr["is_total"] & (tr["account"] == a)]["booked_amount"].sum(),
         ) for a in bk["account"].unique())),
    ]
    closed_by_account = cl[~cl["is_total"]].groupby("account")["realized_gain_loss"].sum()
    trades_by_account = real.groupby("account")["realized_gain_loss"].sum()
    result.append(("Lukkede positioner: realiseret gevinst/tab = handlernes realiseret gevinst/tab pr. konto",
                   all(close(v, trades_by_account.get(a, 0.0)) for a, v in closed_by_account.items())))
    group_ok = True
    for _, rows in ps.groupby(["account", "product_group"]):
        total = rows[rows["is_total"]]
        group_ok &= len(total) == 1 and close(rows[~rows["is_total"]]["market_value"].sum(), total["market_value"].iloc[0])
    result.append(("Beholdninger: positioner summerer til I alt i hver konto og produktgruppe", bool(group_ok)))
    held = ps[~ps["is_total"]]
    traded = set(zip(real["account"], real["instrument"]))
    result.append(("Beholdninger: alle positioner har ISIN", bool(held["isin"].notna().all())))
    result.append(("Beholdninger: hvert papir findes også i handlerne på samme konto",
                   all((a, i) in traded for a, i in zip(held["account"], held["instrument"]))))
    return result


def main(argv: list[str]) -> int:
    if argv:
        path = Path(argv[0])
    else:
        candidates = sorted(Path("data").glob("TransactionBalance_*.pdf"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            print("No TransactionBalance_*.pdf found in data/")
            return 1
        path = candidates[-1]
    tables = parse_transaction_report(path)
    out = Path("output/transactions")
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"{name:18s} {len(df):4d} rows -> {out / (name + '.csv')}")
    print()
    results = checks(tables)
    for description, passed in results:
        print(f"[{'OK' if passed else 'FEJL'}] {description}")
    return 0 if all(passed for _, passed in results) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
