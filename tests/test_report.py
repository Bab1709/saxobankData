"""Tests for the HTML report. All data is made up."""
from saxobank.report import demo_data, dk, kr, nice_ticks, pct, render


def test_danish_number_format():
    assert dk(1234567.891, 2) == "1.234.567,89"
    assert kr(-1500) == "−1.500 kr"
    assert pct(12.34, 1, sign=True) == "+12,3 %"
    assert pct(None) == "–"


def test_nice_ticks_cover_the_data():
    ticks = nice_ticks(0, 112000)
    assert ticks[0] == 0 and ticks[-1] >= 112000
    assert len(set(round(b - a, 6) for a, b in zip(ticks, ticks[1:]))) == 1


def test_demo_report_is_self_contained():
    page = render(demo_data())
    assert page.startswith("<!doctype html>")
    assert "http://" not in page and "https://" not in page
    assert page.count("<svg") == 5
    assert "data-tip=" in page
