"""Rebuild tables from Saxo's PDF reports.

The PDFs have no table lines, so pdfplumber's table finder sees nothing.
Instead every word is read with its position, words are grouped into lines,
and each number is assigned to the column it is right-aligned under.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

# Danish number format: thousands separated by '.', decimals by ','.
_NUMBER = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?%?")
_DATE = re.compile(r"(\d{1,2})-([a-zæøå]{3})\.?-?(\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def page_words(page, x_min: float = 0.0, top_max: float | None = None) -> list[Word]:
    """All words on a pdfplumber page, optionally cropped."""
    words = []
    for w in page.extract_words(x_tolerance=1.5):
        if w["x0"] < x_min or (top_max is not None and w["top"] > top_max):
            continue
        words.append(Word(w["text"], w["x0"], w["x1"], w["top"]))
    return words


def is_number(text: str) -> bool:
    return _NUMBER.fullmatch(text) is not None


def is_amount(text: str) -> bool:
    """A number with decimals, as opposed to a year or an id."""
    return is_number(text) and "," in text


def parse_number(text: str | None) -> float | None:
    """'1.234,56' -> 1234.56, '-12,3%' -> -12.3, '-' or a missing value -> None."""
    if not isinstance(text, str) or not is_number(text):
        return None
    return float(text.rstrip("%").replace(".", "").replace(",", "."))


def parse_date(text: str) -> date | None:
    """'31-dec-2024' -> date(2024, 12, 31)."""
    m = _DATE.search(text)
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    return date(int(m.group(3)), month, int(m.group(1))) if month else None


def merge_percent_signs(line: list[Word]) -> list[Word]:
    """Join a number and a '%' printed as separate words: '12,3' '%' -> '12,3%'."""
    merged: list[Word] = []
    for w in line:
        prev = merged[-1] if merged else None
        if (
            w.text == "%"
            and prev is not None
            and is_number(prev.text)
            and not prev.text.endswith("%")
            and w.x0 - prev.x1 < 4
        ):
            merged[-1] = Word(prev.text + "%", prev.x0, w.x1, prev.top)
        else:
            merged.append(w)
    return merged


def group_lines(words: list[Word], tolerance: float = 3.0) -> list[list[Word]]:
    """Group words into lines by their vertical position, top to bottom."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(lines[-1][0].top - w.top) <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [merge_percent_signs(sorted(line, key=lambda w: w.x0)) for line in lines]


@dataclass(frozen=True)
class Phrase:
    x0: float
    x1: float
    text: str


def header_phrases(lines: list[list[Word]], gap: float = 10.0) -> list[Phrase]:
    """Split header lines into phrases (words less than `gap` apart), and
    merge phrases from stacked header lines that overlap horizontally, so
    'Procentvis' above 'kursændring' becomes one column header."""
    parts: list[list] = []
    for line in lines:
        current = None
        for w in line:
            if current is not None and w.x0 - current[1] <= gap:
                current[1] = w.x1
                current[2].append(w)
            else:
                current = [w.x0, w.x1, [w]]
                parts.append(current)
    parts.sort(key=lambda p: p[0])
    merged: list[list] = []
    for x0, x1, words in parts:
        if merged and x0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], x1)
            merged[-1][2] += words
        else:
            merged.append([x0, x1, list(words)])
    return [
        Phrase(x0, x1, " ".join(w.text for w in sorted(words, key=lambda w: (round(w.top), w.x0))))
        for x0, x1, words in merged
    ]


@dataclass(frozen=True)
class Column:
    name: str
    x0: float
    x1: float
    kind: str = "number"  # "number": right-aligned value, "text": e.g. a currency code

    def takes(self, w: Word, tolerance: float = 4.0) -> bool:
        if self.kind == "text":
            return self.x0 - 10 <= w.xc <= self.x1 + 10 and re.fullmatch(r"[A-Z]{3}", w.text) is not None
        return (is_number(w.text) or w.text == "-") and abs(w.x1 - self.x1) <= tolerance


def build_columns(phrases: list[Phrase], spec: list[tuple]) -> list[Column]:
    """Match header phrases to column names.

    `spec` is a list of (name, header start, kind, optional). Phrases are
    matched left to right, so two headers that start the same way
    ('Markedsværdi' and 'Markedsværdi %') are told apart by order.
    """
    columns, used = [], set()
    for name, start, kind, optional in spec:
        match = next(
            (i for i, p in enumerate(phrases) if i not in used and p.text.startswith(start)),
            None,
        )
        if match is None:
            if optional:
                continue
            found = [p.text for p in phrases]
            raise ValueError(f"Column header {start!r} not found, headers are {found}")
        used.add(match)
        p = phrases[match]
        columns.append(Column(name, p.x0, p.x1, kind))
    return columns


def split_line(line: list[Word], columns: list[Column]) -> tuple[dict[str, str], list[str]]:
    """Assign the words of one line to columns. Returns (values, label words).

    Text columns are only filled on lines that have numbers, so a word in a
    wrapped instrument name is never mistaken for a currency code."""
    values: dict[str, str] = {}
    rest: list[Word] = []
    for w in line:
        col = next(
            (c for c in columns if c.kind == "number" and c.name not in values and c.takes(w)),
            None,
        )
        if col is None:
            rest.append(w)
        else:
            values[col.name] = w.text
    label: list[str] = []
    if any(v != "-" for v in values.values()):
        for w in rest:
            col = next(
                (c for c in columns if c.kind == "text" and c.name not in values and c.takes(w)),
                None,
            )
            if col is None:
                label.append(w.text)
            else:
                values[col.name] = w.text
    else:
        label = [w.text for w in rest]
    return values, label


def assemble_rows(lines: list[list[Word]], columns: list[Column]) -> tuple[list[dict], list[str]]:
    """Turn the lines of a table body into rows.

    A line with at least one value is a row. Text-only lines are pieces of a
    wrapped label: a piece belongs to the row above if that row's label has
    an unclosed '(' (like '(ISIN:' on one line and the code on the next) or
    the piece holds the '(ISIN: ...)' that row is still missing, otherwise
    it starts the label of the next row.

    Returns the rows and any text lines left over after the last row (which
    may be the title of the next table).
    """
    rows: list[dict] = []
    pending: list[str] = []
    for line in lines:
        values, label = split_line(line, columns)
        text = " ".join(label)
        has_values = any(values.get(c.name, "-") != "-" for c in columns if c.kind == "number")
        if has_values or (values and text == "I alt"):
            rows.append({"label": " ".join(pending + [text]).strip(), **values})
            pending = []
        elif text:
            last = rows[-1]["label"] if rows else ""
            unclosed = last.count("(") > last.count(")")
            missing_isin = "(ISIN:" in text and "(ISIN:" not in last
            if rows and not pending and (unclosed or missing_isin):
                rows[-1]["label"] = f"{last} {text}"
            else:
                pending.append(text)
    return rows, pending
