"""Unit tests: holdings, prices, portfolio calculations."""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Holding


class TestHoldingsCRUD:
    """Creating, reading, updating, deleting holdings."""

    def test_set_holding(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 100.0, 2750000)
        holdings = manager.get_holdings(aid)
        assert len(holdings) == 1
        assert holdings[0].ticker == "VTI"
        assert holdings[0].shares == 100.0
        assert holdings[0].cost_basis_cents == 2750000

    def test_set_holding_without_subtype(self, manager: AccountManager):
        """Holdings work on any account type, not just subtypes."""
        aid = manager.add_account("Generic", 1)
        manager.set_holding(aid, "BTC", 1.5, 5000000)
        assert len(manager.get_holdings(aid)) == 1

    def test_update_holding(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 100.0, 2750000)
        manager.set_holding(aid, "VTI", 150.0, 4150000)  # increased position
        h = manager.get_holdings(aid)[0]
        assert h.shares == 150.0
        assert h.cost_basis_cents == 4150000

    def test_delete_holding(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 100.0, 2750000)
        manager.delete_holding(aid, "VTI")
        assert len(manager.get_holdings(aid)) == 0

    def test_get_all_holdings(self, manager: AccountManager):
        a1 = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        a2 = manager.add_account("Roth", 1, account_subtype="retirement")
        manager.set_holding(a1, "VTI", 100.0, 2750000)
        manager.set_holding(a1, "AAPL", 50.0, 750000)
        manager.set_holding(a2, "VT", 200.0, 2100000)
        all_h = manager.get_all_holdings()
        assert len(all_h) == 3

    def test_holdings_empty_account(self, manager: AccountManager):
        aid = manager.add_account("Empty Brokerage", 1, account_subtype="brokerage")
        assert manager.get_holdings(aid) == []


class TestPrices:
    """Price quote CRUD and lookups."""

    def test_save_and_get_price(self, manager: AccountManager):
        manager.save_price("VTI", "2026-05-13", 27500)
        price = manager.get_price("VTI", "2026-05-13")
        assert price == 27500

    def test_get_price_nonexistent(self, manager: AccountManager):
        assert manager.get_price("VVVV", "2026-01-01") is None

    def test_get_latest_price(self, manager: AccountManager):
        manager.save_price("VTI", "2026-01-01", 25000)
        manager.save_price("VTI", "2026-06-01", 28000)
        latest = manager.get_latest_price("VTI")
        assert latest == 28000

    def test_get_latest_price_no_data(self, manager: AccountManager):
        assert manager.get_latest_price("VVVV") is None

    def test_replace_price(self, manager: AccountManager):
        manager.save_price("VTI", "2026-05-13", 27500)
        manager.save_price("VTI", "2026-05-13", 28000)  # same date, new value
        assert manager.get_price("VTI", "2026-05-13") == 28000

    def test_get_holdings_nav(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 100.0, 2750000)
        manager.set_holding(aid, "AAPL", 50.0, 750000)
        nav = manager.get_holdings_nav(aid)
        assert nav == 2750000 + 750000

    def test_holdings_nav_empty(self, manager: AccountManager):
        aid = manager.add_account("Empty", 1, account_subtype="brokerage")
        assert manager.get_holdings_nav(aid) == 0

    def test_holdings_nav_nonexistent_account(self, manager: AccountManager):
        assert manager.get_holdings_nav(99999) == 0


class TestPortfolioValue:
    """Portfolio market value calculations."""

    def test_portfolio_market_value(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 10.0, 275000)
        manager.save_price("VTI", "2026-05-13", 29000)
        mv = manager.portfolio_market_value(aid)
        assert mv == 10 * 29000  # shares × price_cents

    def test_portfolio_value_missing_price(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 10.0, 275000)
        # No price saved — should return None
        assert manager.portfolio_market_value(aid) is None

    def test_portfolio_value_multiple_holdings(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 10.0, 275000)
        manager.set_holding(aid, "AAPL", 5.0, 75000)
        manager.save_price("VTI", "2026-05-13", 29000)
        manager.save_price("AAPL", "2026-05-13", 16500)
        mv = manager.portfolio_market_value(aid)
        assert mv == 10 * 29000 + 5 * 16500

    def test_portfolio_value_empty(self, manager: AccountManager):
        aid = manager.add_account("Empty", 1, account_subtype="brokerage")
        assert manager.portfolio_market_value(aid) == 0

    def test_portfolio_value_nonexistent_account(self, manager: AccountManager):
        assert manager.portfolio_market_value(99999) == 0
