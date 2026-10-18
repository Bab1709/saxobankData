"""Parse Saxo's Porteføljerapport (Portfolio_*.pdf) into tables.

Usage:
    python -m saxobank.portfolio_report [path/to/Portfolio_....pdf]

Without a path, the newest Portfolio_*.pdf in data/ is used. Tables are
written as CSV to output/portfolio/. Only row counts and consistency checks
are printed, never the data itself.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

from saxobank.pdf_layout import (
    Word,
    assemble_rows,
    build_columns,
    group_lines,
    header_phrases,
    is_amount,
    page_words,
    parse_date,
    parse_number,
)

# Pages 3-8 have explanation text on the left and the tables to the right of this x.
TABLE_LEFT = 240.0
# The page footer (address, page number) sits below this.
FOOTER_TOP = 540.0

PERIOD = re.compile(r"[A-Za-z]\d-\d{4}\*?")
ISIN = re.compile(r"\(ISIN:\s*([A-Z]{2}[A-Z0-9]{9}\d)\)")

GAIN_SPEC = [
    ("income", "Indtægter", "number", False),
    ("costs", "Omkostninger", "number", False),
    ("gain_loss", "Gevinst/tab", "number", False),
    ("return_pct", "% Afkast", "number", True),
]
POSITION_SPEC = [
    ("currency", "Instrumentv", "text", False),
    ("quantity", "Antal", "number", False),
    ("fx_rate", "Omregningssats", "number", False),
    ("open_price", "Åbningskurs", "number", False),
    ("price", "Pris", "number", False),
    ("price_change_pct", "Procentvis", "number", False),
    ("unrealized_gain_loss", "Urealiseret", "number", False),
    ("market_value", "Markedsværdi", "number", False),
    ("weight_pct", "Markedsværdi %", "number", False),
]
HOLDINGS_OVERVIEW_SPEC = [
    ("unrealized_gain_loss", "Urealiseret", "number", False),
    ("market_value", "Markedsværdi", "number", False),
    ("weight_pct", "%", "number", False),
]


def _texts(line: list[Word]) -> set[str]:
    return {w.text for w in line}


def _numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for c in columns:
        if c in df:
            df[c] = df[c].map(parse_number)
    return df


# --- Kontooversigt -----------------------------------------------------------

def parse_summary(words: list[Word]) -> pd.DataFrame:
    lines = group_lines(words)
    header = next(l for l in lines if "Nettoindbetalinger" in _texts(l))
    top = header[0].top
    band = [w for w in words if top + 5 < w.top < top + 60]
    dates = [d for d in (parse_date(w.text) for w in band) if d]
    values = sorted((w for w in band if is_amount(w.text)), key=lambda w: w.x0)
    if len(values) != 4 or len(dates) < 2:
        raise ValueError("Unexpected layout on the Kontooversigt page")
    below = sorted((w for w in words if w.top > top + 60 and is_amount(w.text)), key=lambda w: w.top)
    change = next(w for w in below if not w.text.endswith("%"))
    total_return = next(w for w in below if w.text.endswith("%"))
    start_value, gain_loss, net_deposits, end_value = (parse_number(w.text) for w in values)
    return pd.DataFrame([{
        "start_date": dates[0],
        "end_date": dates[-1],
        "start_value": start_value,
        "total_gain_loss": gain_loss,
        "net_deposits": net_deposits,
        "end_value": end_value,
        "change_in_value": parse_number(change.text),
        "total_return_pct": parse_number(total_return.text),
    }])


# --- Grids with labels on the left and dates/periods across the top ----------

def _grid(words: list[Word], is_header) -> list[tuple[list[Word], list[list[Word]]]]:
    """Split a page into (header line, body lines) blocks."""
    lines = group_lines([w for w in words if w.x0 >= TABLE_LEFT])
    starts = [i for i, l in enumerate(lines) if is_header(l)]
    return [
        (lines[i], lines[i + 1:(starts[n + 1] if n + 1 < len(starts) else len(lines))])
        for n, i in enumerate(starts)
    ]


def _grid_rows(body: list[list[Word]]) -> tuple[list[float], list[tuple[str, list[str]]]]:
    """Column centres and (label, values) rows of a grid body. Label text
    can sit a few points above or below its numbers, so label text is
    attached to the nearest line with numbers, if one is close enough."""
    value_lines = [l for l in body if sum(is_amount(w.text) for w in l) >= 3]
    if not value_lines:
        return [], []
    first = [w for w in value_lines[0] if is_amount(w.text)]
    centres = [w.xc for w in first]
    label_right = min(w.x0 for w in first) - 5
    labels: dict[int, list[str]] = {i: [] for i in range(len(value_lines))}
    for line in body:
        text = [w for w in line if w.x1 <= label_right]
        if not text:
            continue
        nearest = min(range(len(value_lines)), key=lambda i: abs(value_lines[i][0].top - line[0].top))
        if abs(value_lines[nearest][0].top - line[0].top) <= 15:
            labels[nearest] += [w.text for w in text]
    rows = []
    for i, line in enumerate(value_lines):
        values: list[str | None] = [None] * len(centres)
        for w in line:
            if w.x1 > label_right and (is_amount(w.text) or w.text == "-"):
                col = min(range(len(centres)), key=lambda c: abs(centres[c] - w.xc))
                if abs(centres[col] - w.xc) < 20:
                    values[col] = w.text
        rows.append((" ".join(labels[i]), values))
    return centres, rows


def parse_account_value(words: list[Word]) -> pd.DataFrame:
    """Udvikling i kontoens værdi: cash, positions and account value by date."""
    words = [w for w in words if w.x0 >= TABLE_LEFT]
    body = group_lines(words)
    centres, rows = _grid_rows(body)
    if not rows:
        raise ValueError("No values found on the Udvikling i kontoens værdi page")
    first_top = next(l for l in body if sum(is_amount(w.text) for w in l) >= 3)[0].top
    label_right = min(centres) - 25
    header = [w for w in words if first_top - 40 < w.top < first_top - 3 and w.x0 > label_right]
    dates = []
    for c in centres:
        parts = sorted((w for w in header if abs(w.xc - c) < 22), key=lambda w: (w.top, w.x0))
        dates.append(parse_date("".join(w.text for w in parts)))
    names = {
        "Kontanter": "cash",
        "Akkumulerede": "unbooked",
        "Positionsværdi": "positions",
        "Kontoens": "account_value",
    }
    table = {"date": dates}
    for label, values in rows:
        key = next((v for k, v in names.items() if label.startswith(k)), label)
        table[key] = [parse_number(v) for v in values]
    return pd.DataFrame(table)


def parse_period_returns(words: list[Word]) -> pd.DataFrame:
    """Udvikling i samlet gevinst/tab: % return and gain/loss per period.
    A period marked '*' in the report only covers part of the period."""
    blocks = _grid(words, lambda l: sum(PERIOD.fullmatch(w.text) is not None for w in l) >= 3)
    if not blocks:
        raise ValueError("No period table found")
    table: dict[str, list] = {}
    for header, body in blocks:
        centres, rows = _grid_rows(body)
        periods = []
        for c in centres:
            near = [w.text for w in header if PERIOD.fullmatch(w.text) and abs(w.xc - c) < 20]
            periods.append(near[0] if near else "Total")
        if "period" not in table:
            table["period"] = [p.rstrip("*") for p in periods]
            table["partial"] = [p.endswith("*") for p in periods]
        elif [p.rstrip("*") for p in periods] != table["period"]:
            raise ValueError("The period tables have different columns")
        for label, values in rows:
            table[_period_row_name(label)] = [parse_number(v) for v in values]
    return pd.DataFrame(table)


def _period_row_name(label: str) -> str:
    # A footnote ('*Delperiode') is printed on top of the row labels, so the
    # label text is garbled and only its first words can be relied on.
    if "Afkast" in label:
        return "return_pct"
    if "Samlede" in label:
        return "costs"
    if "Samlet" in label:
        return "gain_loss"
    raise ValueError(f"Unknown row in the period table: {label!r}")


# --- Fordeling af gevinst/tab -------------------------------------------------

def parse_gain_tables(pages: list[list[Word]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gain/loss by product type and by instrument."""
    products, instruments = [], []
    for words in pages:
        lines = group_lines([w for w in words if w.x0 >= TABLE_LEFT])
        starts = [i for i, l in enumerate(lines) if {"Indtægter", "Omkostninger", "Gevinst/tab"} <= _texts(l)]
        if not starts:
            continue
        before = [" ".join(w.text for w in l) for l in lines[:starts[0]] if not any(is_amount(w.text) for w in l)]
        title = before[-1] if before else ""
        for n, i in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(lines)
            phrases = header_phrases([lines[i]])
            columns = build_columns(phrases, GAIN_SPEC)
            rows, pending = assemble_rows(lines[i + 1:end], columns)
            if phrases[0].text.startswith("Produkttype"):
                products += rows
            else:
                instruments += [{"product_group": title, **r} for r in rows]
            title = pending[-1] if pending else title
    value_columns = [s[0] for s in GAIN_SPEC]
    product_df = _numeric(pd.DataFrame(products), value_columns).rename(columns={"label": "product_type"})
    instrument_df = _numeric(pd.DataFrame(instruments), value_columns).rename(columns={"label": "instrument"})
    product_df["is_total"] = product_df["product_type"] == "I alt"
    instrument_df["is_total"] = instrument_df["instrument"] == "I alt"
    return product_df, instrument_df


# --- Beholdninger -------------------------------------------------------------

def parse_holdings(pages: list[list[Word]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Current holdings: an overview by product, and every position."""
    overview, positions = [], []
    group = ""
    for words in pages:
        lines = group_lines(words)
        i = 0
        while i < len(lines):
            texts = _texts(lines[i])
            if "Åbningskurs" in texts:
                kind, spec = "positions", POSITION_SPEC
            elif lines[i][0].text == "Produkt" and "Urealiseret" in texts:
                kind, spec = "overview", HOLDINGS_OVERVIEW_SPEC
            else:
                i += 1
                continue
            # The header can be spread over the lines just above and below.
            top = lines[i][0].top
            band = [l for l in lines if abs(l[0].top - top) <= 9]
            before = [
                " ".join(w.text for w in l) for l in lines[:i]
                if l not in band and not any(is_amount(w.text) for w in l)
            ]
            if kind == "positions" and before:
                group = before[-1]
            columns = build_columns(header_phrases(band)[1:], spec)
            j = max(lines.index(l) for l in band) + 1
            end = j
            while end < len(lines) and not _is_any_header(lines[end]):
                end += 1
            rows, _ = assemble_rows(lines[j:end], columns)
            if kind == "positions":
                positions += [{"product_group": group, **r} for r in rows]
            else:
                overview += rows
            i = end
    overview_df = _numeric(pd.DataFrame(overview), [s[0] for s in HOLDINGS_OVERVIEW_SPEC])
    overview_df = overview_df.rename(columns={"label": "product"})
    overview_df["is_total"] = overview_df["product"] == "I alt"

    positions_df = _numeric(pd.DataFrame(positions), [s[0] for s in POSITION_SPEC if s[2] == "number"])
    positions_df["isin"] = positions_df["label"].str.extract(ISIN, expand=False)
    positions_df["instrument"] = positions_df["label"].str.replace(ISIN, "", regex=True).str.strip()
    # Total rows print '-' in the columns that have no total.
    positions_df["is_total"] = positions_df["instrument"].str.match(r"I alt( -)*$")
    positions_df.loc[positions_df["is_total"], "instrument"] = "I alt"
    positions_df = positions_df.drop(columns="label")
    first = ["product_group", "instrument", "isin", "currency"]
    positions_df = positions_df[first + [c for c in positions_df if c not in first]]
    return overview_df, positions_df


def _is_any_header(line: list[Word]) -> bool:
    texts = _texts(line)
    return (
        "Åbningskurs" in texts
        or (line[0].text == "Produkt" and "Urealiseret" in texts)
        or {"Konto", "Valuta", "Værdi"} <= texts
        or "Instrumentv" in texts
    )


# --- Whole report -------------------------------------------------------------

def _find(pages: list[list[Word]], test) -> list[int]:
    return [i for i, words in enumerate(pages) if test(words)]


def parse_portfolio_report(path: Path) -> dict[str, pd.DataFrame]:
    with pdfplumber.open(path) as pdf:
        # Page 1 only holds name and address, so it is never read.
        pages = [page_words(p, top_max=FOOTER_TOP) for p in pdf.pages[1:]]

    def has(*texts):
        return lambda words: set(texts) <= {w.text for w in words}

    summary_page = _find(pages, has("Nettoindbetalinger"))[0]
    value_page = _find(pages, lambda ws: {"Positionsværdi", "Kontanter"} <= {w.text for w in ws if w.x0 >= TABLE_LEFT})[0]
    period_page = _find(pages, lambda ws: sum(PERIOD.fullmatch(w.text) is not None for w in ws) >= 6)[0]
    gain_pages = _find(pages, has("Indtægter", "Omkostninger", "Gevinst/tab"))
    holding_pages = _find(pages, lambda ws: "Åbningskurs" in {w.text for w in ws} or has("Produkt", "Urealiseret")(ws))

    gain_by_product, gain_by_instrument = parse_gain_tables([pages[i] for i in gain_pages])
    holdings_overview, positions = parse_holdings([pages[i] for i in holding_pages])
    return {
        "summary": parse_summary(pages[summary_page]),
        "account_value": parse_account_value(pages[value_page]),
        "period_returns": parse_period_returns(pages[period_page]),
        "gain_by_product": gain_by_product,
        "gain_by_instrument": gain_by_instrument,
        "holdings_overview": holdings_overview,
        "positions": positions,
    }


def checks(tables: dict[str, pd.DataFrame]) -> list[tuple[str, bool]]:
    """Consistency checks against the report's own totals. Returns
    (description, passed) pairs, without any amounts."""
    def close(a, b, tol=1.0):
        return a is not None and b is not None and abs(a - b) <= tol

    s = tables["summary"].iloc[0]
    av = tables["account_value"]
    pr = tables["period_returns"]
    gp = tables["gain_by_product"]
    gi = tables["gain_by_instrument"]
    ho = tables["holdings_overview"]
    pos = tables["positions"]

    result = [
        ("Kontooversigt: start + gevinst/tab + nettoindbetalinger = slutværdi",
         close(s.start_value + s.total_gain_loss + s.net_deposits, s.end_value)),
        ("Kontooversigt: slutværdi - startværdi = ændring i kontoens værdi",
         close(s.end_value - s.start_value, s.change_in_value)),
        ("Kontoens værdi: alle datoer fundet", av["date"].notna().all()),
        ("Kontoens værdi: kontanter + ikke-bogførte + positioner = kontoens værdi på alle datoer",
         bool(((av["cash"] + av["unbooked"] + av["positions"] - av["account_value"]).abs() <= 1).all())),
        ("Kontoens værdi: sidste dato = slutværdi i kontooversigten",
         close(av["account_value"].iloc[-1], s.end_value)),
    ]
    periods = pr[pr["period"] != "Total"]
    total = pr[pr["period"] == "Total"]
    compounded = ((1 + periods["return_pct"] / 100).prod() - 1) * 100
    result += [
        ("Perioder: sammensat afkast = samlet afkast (±0,5 %-point)",
         len(total) == 1 and close(compounded, total["return_pct"].iloc[0], 0.5)),
        ("Perioder: samlet afkast = afkast i kontooversigten (±0,1 %-point)",
         len(total) == 1 and close(total["return_pct"].iloc[0], s.total_return_pct, 0.1)),
        ("Perioder: sum af gevinst/tab = total",
         len(total) == 1 and close(periods["gain_loss"].sum(), total["gain_loss"].iloc[0], len(periods))),
        ("Perioder: total gevinst/tab = gevinst/tab i kontooversigten",
         len(total) == 1 and close(total["gain_loss"].iloc[0], s.total_gain_loss)),
        ("Perioder: sum af omkostninger = total",
         len(total) == 1 and close(periods["costs"].sum(), total["costs"].iloc[0], len(periods))),
    ]
    product_total = gp[gp["is_total"]]
    result.append(("Gevinst pr. produkttype: rækker summerer til I alt",
                   len(product_total) == 1 and close(gp[~gp["is_total"]]["gain_loss"].sum(), product_total["gain_loss"].iloc[0])))
    group_ok = True
    for group, rows in gi.groupby("product_group"):
        tot = rows[rows["is_total"]]
        group_ok &= len(tot) == 1 and close(rows[~rows["is_total"]]["gain_loss"].sum(), tot["gain_loss"].iloc[0])
    result.append(("Gevinst pr. instrument: hver produktgruppe summerer til sin I alt", bool(group_ok)))
    overview_total = ho[ho["is_total"]]
    result.append(("Beholdninger: oversigt summerer til I alt",
                   len(overview_total) == 1 and close(ho[~ho["is_total"]]["market_value"].sum(), overview_total["market_value"].iloc[0])))
    group_ok = True
    for group, rows in pos.groupby("product_group"):
        tot = rows[rows["is_total"]]
        group_ok &= len(tot) == 1 and close(rows[~rows["is_total"]]["market_value"].sum(), tot["market_value"].iloc[0])
    result.append(("Beholdninger: positioner summerer til I alt i hver produktgruppe", bool(group_ok)))
    overview_value = ho.set_index("product")["market_value"]
    result.append(("Beholdninger: hver produktgruppe = samme produkt i oversigten",
                   all(close(rows[~rows["is_total"]]["market_value"].sum(), overview_value.get(group))
                       for group, rows in pos.groupby("product_group"))))
    result.append(("Beholdninger: I alt i oversigten = slutværdi i kontooversigten",
                   len(overview_total) == 1 and close(overview_total["market_value"].iloc[0], s.end_value)))
    result.append(("Beholdninger: alle positioner har ISIN og valuta",
                   bool(pos[~pos["is_total"]][["isin", "currency"]].notna().all().all())))
    return result


def main(argv: list[str]) -> int:
    if argv:
        path = Path(argv[0])
    else:
        candidates = sorted(Path("data").glob("Portfolio_*.pdf"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            print("No Portfolio_*.pdf found in data/")
            return 1
        path = candidates[-1]
    tables = parse_portfolio_report(path)
    out = Path("output/portfolio")
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"{name:20s} {len(df):4d} rows -> {out / (name + '.csv')}")
    print()
    results = checks(tables)
    for description, passed in results:
        print(f"[{'OK' if passed else 'FEJL'}] {description}")
    return 0 if all(passed for _, passed in results) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
