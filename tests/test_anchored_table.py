"""Tests for tables whose cells wrap over several lines. All data is made up."""
from saxobank.pdf_layout import Field, Word, group_lines, read_anchored_table, rejoin_split_cells

FIELDS = [
    Field("date", "Dato", "left"),
    Field("instrument", "Instrument", "centre"),
    Field("amount", "Beløb", "number"),
]
HEADER = [[Word("Dato", 20, 50, 100), Word("Instrument", 100, 150, 100), Word("Beløb", 230, 260, 100)]]


def is_anchor(cells):
    return any(w.text.startswith("01-") for w in cells.get("date", []))


def test_wrapped_cells_join_their_row():
    body = group_lines([
        Word("Fake", 105, 125, 120), Word("Holding", 127, 160, 120),
        Word("01-jan-2024", 20, 60, 126), Word("1.000,00", 220, 260, 126),
        Word("A/S", 115, 135, 132),
        Word("Other", 110, 135, 150),
        Word("01-feb-2024", 20, 60, 156), Word("-500,00", 225, 260, 156),
    ])
    rows, leading = read_anchored_table(HEADER, body, FIELDS, is_anchor)
    assert rows == [
        {"date": "01-jan-2024", "instrument": "Fake Holding A/S", "amount": "1.000,00"},
        {"date": "01-feb-2024", "instrument": "Other", "amount": "-500,00"},
    ]
    assert leading == {}


def test_short_word_far_left_stays_in_its_cell():
    # 'AB' alone would fall left of the instrument column, but it is part of
    # a run of words whose centre is inside it.
    body = group_lines([
        Word("AB", 80, 90, 120), Word("Fake", 92, 110, 120), Word("Long", 112, 130, 120),
        Word("Name", 132, 150, 120), Word("Fund", 152, 175, 120),
        Word("01-jan-2024", 20, 60, 126), Word("1,00", 240, 260, 126),
    ])
    rows, _ = read_anchored_table(HEADER, body, FIELDS, is_anchor)
    assert rows[0]["instrument"] == "AB Fake Long Name Fund"


def test_footnotes_and_far_lines_are_not_joined():
    body = group_lines([
        Word("01-jan-2024", 20, 60, 126), Word("1,00", 240, 260, 126),
        Word("*", 20, 23, 140), Word("Footnote", 25, 60, 140),
    ])
    rows, _ = read_anchored_table(HEADER, body, FIELDS, is_anchor)
    assert "date" in rows[0] and rows[0].get("instrument") is None


def test_text_above_first_row_is_returned_as_leading():
    body = group_lines([
        Word("XX0000000001)", 105, 160, 105),
        Word("01-jan-2024", 20, 60, 160), Word("1,00", 240, 260, 160),
    ])
    rows, leading = read_anchored_table(HEADER, body, FIELDS, is_anchor)
    assert leading == {"instrument": "XX0000000001)"}
    assert len(rows) == 1


def test_rejoin_split_cells_moves_text_back_across_page_break():
    rows = [{"instrument": "Fake A/S (ISIN:"}, {"instrument": "XX0000000001) Next Fund"}]
    rejoin_split_cells(rows, "instrument")
    assert rows == [{"instrument": "Fake A/S (ISIN: XX0000000001)"}, {"instrument": "Next Fund"}]
