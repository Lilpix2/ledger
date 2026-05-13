"""Unit tests: holdings, prices, portfolio calculations.

All tests use the ``fast_manager`` fixture (MockDB, no disk I/O).
Follows strict AAA pattern (Arrange, Act, Assert) with descriptive naming.
"""

import pytest

from ledger.controllers.accounts import AccountManager


class TestHoldingsCRUD:
    """Creating, reading, updating, deleting holdings."""

    def test_set_holding_createsPosition_returnsOneHolding(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange"""
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        """Act"""
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        holdings = fast_manager.get_holdings(aid)
        """Assert"""
        assert len(holdings) == 1
        assert holdings[0].ticker == "VTI"
        assert holdings[0].shares == 100.0
        assert holdings[0].cost_basis_cents == 2750000

    def test_set_holding_anyAccountType_createsHolding(
        self, fast_manager: AccountManager,
    ) -> None:
        """Holdings work on any account type, not just subtypes."""
        aid = fast_manager.add_account("Generic", 1)
        fast_manager.set_holding(aid, "BTC", 1.5, 5000000)
        assert len(fast_manager.get_holdings(aid)) == 1

    def test_set_holding_nonexistentAccount_raisesValueError(
        self, fast_manager: AccountManager,
    ) -> None:
        with pytest.raises(ValueError, match="No account with ID"):
            fast_manager.set_holding(99999, "VTI", 10.0, 250000)

    def test_update_holding_sameTicker_overwritesPosition(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        fast_manager.set_holding(aid, "VTI", 150.0, 4150000)
        h = fast_manager.get_holdings(aid)[0]
        assert h.shares == 150.0
        assert h.cost_basis_cents == 4150000

    def test_delete_holding_removesPosition_returnsEmpty(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        fast_manager.delete_holding(aid, "VTI")
        assert len(fast_manager.get_holdings(aid)) == 0

    def test_delete_holding_nonexistentTicker_doesNotRaise(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        fast_manager.delete_holding(aid, "NONEXIST")
        assert len(fast_manager.get_holdings(aid)) == 1

    def test_get_all_holdings_multipleAccounts_returnsAll(
        self, fast_manager: AccountManager,
    ) -> None:
        a1 = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        a2 = fast_manager.add_account("Roth", 1, account_subtype="retirement")
        fast_manager.set_holding(a1, "VTI", 100.0, 2750000)
        fast_manager.set_holding(a1, "AAPL", 50.0, 750000)
        fast_manager.set_holding(a2, "VT", 200.0, 2100000)
        all_h = fast_manager.get_all_holdings()
        assert len(all_h) == 3

    def test_get_all_holdings_noHoldings_returnsEmpty(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager.get_all_holdings() == []

    def test_get_holdings_emptyAccount_returnsEmptyList(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Empty Brokerage", 1, account_subtype="brokerage")
        assert fast_manager.get_holdings(aid) == []

    def test_get_holdings_nonexistentAccount_raisesValueError(
        self, fast_manager: AccountManager,
    ) -> None:
        with pytest.raises(ValueError, match="No account with ID"):
            fast_manager.get_holdings(99999)


class TestPrices:
    """Price quote CRUD and lookups."""

    def test_save_and_get_price_roundTrip_returnsPrice(
        self, fast_manager: AccountManager,
    ) -> None:
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        price = fast_manager.get_price("VTI", "2026-05-13")
        assert price == 27500

    def test_get_price_nonexistentDate_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        assert fast_manager.get_price("VTI", "2026-01-01") is None

    def test_get_price_nonexistentTicker_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager.get_price("VVVV", "2026-01-01") is None

    def test_get_latest_price_multipleQuotes_returnsMostRecent(
        self, fast_manager: AccountManager,
    ) -> None:
        fast_manager.save_price("VTI", "2026-01-01", 25000)
        fast_manager.save_price("VTI", "2026-06-01", 28000)
        latest = fast_manager.get_latest_price("VTI")
        assert latest == 28000

    def test_get_latest_price_noData_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager.get_latest_price("VVVV") is None

    def test_replace_price_sameDateOverwrites_returnsNewPrice(
        self, fast_manager: AccountManager,
    ) -> None:
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        fast_manager.save_price("VTI", "2026-05-13", 28000)
        assert fast_manager.get_price("VTI", "2026-05-13") == 28000

    def test_get_holdings_nav_multiplePositions_returnsSum(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        fast_manager.set_holding(aid, "AAPL", 50.0, 750000)
        nav = fast_manager.get_holdings_nav(aid)
        assert nav == 2750000 + 750000

    def test_get_holdings_nav_emptyAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Empty", 1, account_subtype="brokerage")
        assert fast_manager.get_holdings_nav(aid) == 0

    def test_get_holdings_nav_nonexistentAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager.get_holdings_nav(99999) == 0


class TestPortfolioValue:
    """Portfolio market value calculations."""

    def test_portfolio_market_value_singleHolding_returnsProduct(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        mv = fast_manager.portfolio_market_value(aid)
        assert mv == 10 * 29000

    def test_portfolio_market_value_missingPrice_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        assert fast_manager.portfolio_market_value(aid) is None

    def test_portfolio_market_value_multipleHoldings_returnsSum(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.set_holding(aid, "AAPL", 5.0, 75000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        fast_manager.save_price("AAPL", "2026-05-13", 16500)
        mv = fast_manager.portfolio_market_value(aid)
        assert mv == 10 * 29000 + 5 * 16500

    def test_portfolio_market_value_emptyAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Empty", 1, account_subtype="brokerage")
        assert fast_manager.portfolio_market_value(aid) == 0

    def test_portfolio_market_value_nonexistentAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager.portfolio_market_value(99999) == 0
