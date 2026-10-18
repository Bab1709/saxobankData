"""Tests for the return calculations. All data is made up."""
from datetime import date

import pandas as pd
import pytest

from saxobank.returns import account_returns, instrument_returns, xirr


def test_xirr_one_year():
    assert xirr([(date(2023, 1, 1), -1000.0), (date(2024, 1, 1), 1100.0)]) == pytest.approx(10.0, abs=0.05)


def test_xirr_needs_money_in_and_out():
    assert xirr([(date(2023, 1, 1), -1000.0)]) is None
    assert xirr([(date(2023, 1, 1), 1000.0), (date(2024, 1, 1), 1000.0)]) is None


def _trades(rows):
    columns = ["account", "trade_date", "value_date", "product", "instrument", "event_type",
               "booked_amount", "booked_costs", "realized_gain_loss", "is_total"]
    return pd.DataFrame(rows, columns=columns)


def test_instrument_returns_open_position():
    trades = _trades([
        ("FAKE-ACCOUNT-1", date(2023, 1, 2), date(2023, 1, 4), "Aktie", "Fake A/S", "Købt", -1010.0, -10.0, 0.0, False),
        ("FAKE-ACCOUNT-1", date(2023, 6, 1), date(2023, 6, 1), "Aktie", "Fake A/S", "Kontantudbytte", 50.0, 0.0, 0.0, False),
        ("FAKE-ACCOUNT-1", date(2023, 1, 2), date(2023, 1, 2), "Kontanter", None, "Indbetaling", 2000.0, 0.0, 0.0, False),
    ])
    positions = pd.DataFrame([
        {"account": "FAKE-ACCOUNT-1", "instrument": "Fake A/S", "isin": "XX0000000001", "market_value": 1100.0, "is_total": False},
    ])
    result = instrument_returns(trades, positions, date(2024, 1, 4)).iloc[0]
    assert result["invested"] == 1010.0
    assert result["dividends"] == 50.0
    assert result["costs"] == 10.0
    assert result["gain_loss"] == pytest.approx(140.0)
    assert result["return_pct"] == pytest.approx(140.0 / 1010.0 * 100)
    assert result["status"] == "åben"


def test_account_returns_uses_deposits_and_value_today():
    trades = _trades([
        ("FAKE-ACCOUNT-1", date(2023, 1, 2), date(2023, 1, 2), "Kontanter", None, "Indbetaling", 2000.0, 0.0, 0.0, False),
        ("FAKE-ACCOUNT-1", date(2023, 1, 2), date(2023, 1, 4), "Aktie", "Fake A/S", "Købt", -1010.0, -10.0, 0.0, False),
    ])
    positions = pd.DataFrame([{"account": "FAKE-ACCOUNT-1", "market_value": 1100.0, "is_total": False}])
    bookings = pd.DataFrame([{"account": "FAKE-ACCOUNT-1", "total": 990.0, "is_total": True}])
    result = account_returns(trades, positions, bookings, date(2024, 1, 2)).set_index("account")
    assert result.loc["FAKE-ACCOUNT-1", "value"] == 2090.0
    assert result.loc["FAKE-ACCOUNT-1", "gain_loss"] == 90.0
    assert result.loc["I alt", "net_deposits"] == 2000.0
