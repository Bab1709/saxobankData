"""Tests for rebuilding tables from word positions. All data is made up."""
from datetime import date

from saxobank.pdf_layout import (
    Column,
    Word,
    assemble_rows,
    build_columns,
    group_lines,
    header_phrases,
    parse_date,
    parse_number,
)


def w(text, x0, x1, top):
    return Word(text, x0, x1, top)


def test_parse_number_danish_format():
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("-12,5%") == -12.5
    assert parse_number("1.000") == 1000
    assert parse_number("-") is None
    assert parse_number(None) is None
    assert parse_number("FAKE") is None


def test_parse_date_danish_months():
    assert parse_date("01-maj-2024") == date(2024, 5, 1)
    assert parse_date("31-okt-" + "2025") == date(2025, 10, 31)
    assert parse_date("nothing here") is None


def test_group_lines_merges_percent_sign():
    lines = group_lines([w("%", 52, 58, 101), w("10,0", 30, 50, 100), w("Label", 0, 20, 100)])
    assert [x.text for x in lines[0]] == ["Label", "10,0%"]


def test_header_phrases_merge_stacked_headers_top_to_bottom():
    upper = [w("Procentvis", 100, 140, 10)]
    lower = [w("Instrument", 0, 40, 16), w("kursændring", 95, 140, 22)]
    phrases = header_phrases([upper, lower])
    assert [p.text for p in phrases] == ["Instrument", "Procentvis kursændring"]


def test_build_columns_tells_similar_headers_apart_by_order():
    phrases = header_phrases([[w("Markedsværdi", 100, 150, 0), w("Markedsværdi", 200, 250, 0), w("%", 252, 258, 0)]])
    spec = [("value", "Markedsværdi", "number", False), ("weight", "Markedsværdi %", "number", False)]
    columns = build_columns(phrases, spec)
    assert [(c.name, c.x1) for c in columns] == [("value", 150), ("weight", 258)]


def test_assemble_rows_wrapped_names_and_isin():
    columns = [Column("currency", 100, 120, "text"), Column("value", 180, 200)]
    lines = group_lines([
        # Name before the numbers, '(ISIN:' left open, code on the next line.
        w("Fake", 0, 20, 10), w("Company", 22, 60, 10),
        w("A/S", 0, 15, 20), w("(ISIN:", 17, 40, 20), w("DKK", 104, 116, 20), w("1.000,00", 160, 200, 20),
        w("XX0000000001)", 0, 60, 30),
        # Second row: the ISIN comes after the numbers, at the end of the name.
        w("Other", 0, 25, 40), w("Fund", 27, 45, 40),
        w("EUR", 104, 116, 50), w("500,00", 170, 200, 50),
        w("KL", 0, 10, 60), w("(ISIN:", 12, 35, 60), w("XX0000000002)", 37, 90, 60),
        w("I", 0, 3, 70), w("alt", 5, 15, 70), w("1.500,00", 160, 200, 70),
    ])
    rows, pending = assemble_rows(lines, columns)
    assert rows == [
        {"label": "Fake Company A/S (ISIN: XX0000000001)", "currency": "DKK", "value": "1.000,00"},
        {"label": "Other Fund KL (ISIN: XX0000000002)", "currency": "EUR", "value": "500,00"},
        {"label": "I alt", "value": "1.500,00"},
    ]
    assert pending == []


def test_assemble_rows_returns_text_after_last_row():
    columns = [Column("value", 180, 200)]
    lines = group_lines([w("Row", 0, 20, 10), w("1,00", 180, 200, 10), w("Next", 0, 20, 30), w("title", 22, 40, 30)])
    rows, pending = assemble_rows(lines, columns)
    assert rows == [{"label": "Row", "value": "1,00"}]
    assert pending == ["Next title"]
