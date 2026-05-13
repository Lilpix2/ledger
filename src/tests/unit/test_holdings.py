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
        """Arrange: brokerage account. Act: set VTI holding. Assert: 1 holding stored."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # Act
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        holdings = fast_manager.get_holdings(aid)
        # Assert
        assert len(holdings) == 1
        assert holdings[0].ticker == "VTI"
        assert holdings[0].shares == 100.0
        assert holdings[0].cost_basis_cents == 2750000

    def test_set_holding_anyAccountType_createsHolding(
        self, fast_manager: AccountManager,
    ) -> None:
        """Holdings work on any account type, not just subtypes."""
        # Arrange
        aid = fast_manager.add_account("Generic", 1)
        # Act
        fast_manager.set_holding(aid, "BTC", 1.5, 5000000)
        # Assert
        assert len(fast_manager.get_holdings(aid)) == 1

    def test_set_holding_nonexistentAccount_raisesValueError(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no account 99999. Act: set_holding with bad ID. Assert: ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="No account with ID"):
            fast_manager.set_holding(99999, "VTI", 10.0, 250000)

    def test_set_holding_zeroShares_createsPosition(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: brokerage account. Act: set holding with 0 shares. Assert: stored."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # Act
        fast_manager.set_holding(aid, "VTI", 0.0, 0)
        # Assert
        holdings = fast_manager.get_holdings(aid)
        assert len(holdings) == 1
        assert holdings[0].shares == 0.0

    def test_set_holding_negativeShares_stored(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: brokerage account. Act: set holding with -5 shares. Assert: stored as-is."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # Act
        fast_manager.set_holding(aid, "VTI", -5.0, 1000)
        # Assert
        assert fast_manager.get_holdings(aid)[0].shares == -5.0

    def test_set_holding_zeroCostBasis_createsPosition(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: brokerage account. Act: set holding with 0 cost basis. Assert: stored."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # Act
        fast_manager.set_holding(aid, "VTI", 10.0, 0)
        # Assert
        assert fast_manager.get_holdings(aid)[0].cost_basis_cents == 0

    def test_update_holding_sameTicker_overwritesPosition(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: set VTI 100@275. Act: set same ticker 150@415. Assert: overwritten."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        # Act
        fast_manager.set_holding(aid, "VTI", 150.0, 4150000)
        h = fast_manager.get_holdings(aid)[0]
        # Assert
        assert h.shares == 150.0
        assert h.cost_basis_cents == 4150000

    def test_delete_holding_removesPosition_returnsEmpty(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: set VTI. Act: delete_holding. Assert: no holdings remain."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        # Act
        fast_manager.delete_holding(aid, "VTI")
        # Assert
        assert len(fast_manager.get_holdings(aid)) == 0

    def test_delete_holding_nonexistentTicker_doesNotRaise(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: set VTI. Act: delete nonexistent ticker. Assert: VTI still present."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        # Act
        fast_manager.delete_holding(aid, "NONEXIST")
        # Assert
        assert len(fast_manager.get_holdings(aid)) == 1

    def test_delete_holding_nonexistentAccount_doesNotRaise(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no holdings. Act: delete_holding on nonexistent account. Assert: no error."""
        # Arrange & Act
        fast_manager.delete_holding(99999, "VTI")
        # Assert — no exception raised

    def test_get_all_holdings_multipleAccounts_returnsAll(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: two accounts with holdings. Act: get_all_holdings. Assert: 3 holdings."""
        # Arrange
        a1 = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        a2 = fast_manager.add_account("Roth", 1, account_subtype="retirement")
        fast_manager.set_holding(a1, "VTI", 100.0, 2750000)
        fast_manager.set_holding(a1, "AAPL", 50.0, 750000)
        fast_manager.set_holding(a2, "VT", 200.0, 2100000)
        # Act
        all_h = fast_manager.get_all_holdings()
        # Assert
        assert len(all_h) == 3

    def test_get_all_holdings_noHoldings_returnsEmpty(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: fresh manager. Act: get_all_holdings. Assert: empty list."""
        # Arrange — no holdings set
        # Act & Assert
        assert fast_manager.get_all_holdings() == []

    def test_get_holdings_emptyAccount_returnsEmptyList(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: account with no holdings. Act: get_holdings. Assert: empty list."""
        # Arrange
        aid = fast_manager.add_account("Empty Brokerage", 1, account_subtype="brokerage")
        # Act & Assert
        assert fast_manager.get_holdings(aid) == []

    def test_get_holdings_nonexistentAccount_raisesValueError(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no account. Act: get_holdings(99999). Assert: ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="No account with ID"):
            fast_manager.get_holdings(99999)


class TestPrices:
    """Price quote CRUD and lookups."""

    def test_save_and_get_price_roundTrip_returnsPrice(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: save VTI price. Act: get_price. Assert: same price returned."""
        # Arrange
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        # Act
        price = fast_manager.get_price("VTI", "2026-05-13")
        # Assert
        assert price == 27500

    def test_get_price_nonexistentDate_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: save one price. Act: query different date. Assert: None."""
        # Arrange
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        # Act & Assert
        assert fast_manager.get_price("VTI", "2026-01-01") is None

    def test_get_price_nonexistentTicker_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no prices. Act: query ticker VVVV. Assert: None."""
        # Arrange — no prices saved
        # Act & Assert
        assert fast_manager.get_price("VVVV", "2026-01-01") is None

    def test_get_price_emptyTicker_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no prices. Act: query empty string ticker. Assert: None."""
        # Arrange & Act & Assert
        assert fast_manager.get_price("", "2026-01-01") is None

    def test_get_latest_price_multipleQuotes_returnsMostRecent(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: two prices. Act: get_latest_price. Assert: most recent returned."""
        # Arrange
        fast_manager.save_price("VTI", "2026-01-01", 25000)
        fast_manager.save_price("VTI", "2026-06-01", 28000)
        # Act
        latest = fast_manager.get_latest_price("VTI")
        # Assert
        assert latest == 28000

    def test_get_latest_price_singleQuote_returnsThatPrice(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: one price saved. Act: get_latest_price. Assert: that price."""
        # Arrange
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        # Act & Assert
        assert fast_manager.get_latest_price("VTI") == 27500

    def test_get_latest_price_noData_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no prices. Act: get_latest_price. Assert: None."""
        # Arrange — no prices saved
        # Act & Assert
        assert fast_manager.get_latest_price("VVVV") is None

    def test_replace_price_sameDateOverwrites_returnsNewPrice(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: save price @ 27500. Act: save same date @ 28000. Assert: 28000."""
        # Arrange
        fast_manager.save_price("VTI", "2026-05-13", 27500)
        # Act
        fast_manager.save_price("VTI", "2026-05-13", 28000)
        # Assert
        assert fast_manager.get_price("VTI", "2026-05-13") == 28000

    def test_get_holdings_nav_multiplePositions_returnsSum(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: two holdings. Act: get_holdings_nav. Assert: sum of cost bases."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 2750000)
        fast_manager.set_holding(aid, "AAPL", 50.0, 750000)
        # Act
        nav = fast_manager.get_holdings_nav(aid)
        # Assert
        assert nav == 2750000 + 750000

    def test_get_holdings_nav_singleHolding_returnsCostBasis(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: one holding. Act: get_holdings_nav. Assert: equals its cost basis."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        # Act & Assert
        assert fast_manager.get_holdings_nav(aid) == 275000

    def test_get_holdings_nav_emptyAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: account with no holdings. Act: get_holdings_nav. Assert: 0."""
        # Arrange
        aid = fast_manager.add_account("Empty", 1, account_subtype="brokerage")
        # Act & Assert
        assert fast_manager.get_holdings_nav(aid) == 0

    def test_get_holdings_nav_nonexistentAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no account. Act: get_holdings_nav(99999). Assert: 0."""
        # Arrange & Act & Assert
        assert fast_manager.get_holdings_nav(99999) == 0


class TestPortfolioValue:
    """Portfolio market value calculations."""

    def test_portfolio_market_value_singleHolding_returnsProduct(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: one holding + price. Act: portfolio_market_value. Assert: shares * price."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        # Act
        mv = fast_manager.portfolio_market_value(aid)
        # Assert
        assert mv == 10 * 29000

    def test_portfolio_market_value_missingPrice_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: holding, no price. Act: portfolio_market_value. Assert: None."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        # Act & Assert
        assert fast_manager.portfolio_market_value(aid) is None

    def test_portfolio_market_value_multipleHoldings_returnsSum(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: two holdings + prices. Act: portfolio_market_value. Assert: sum."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.set_holding(aid, "AAPL", 5.0, 75000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        fast_manager.save_price("AAPL", "2026-05-13", 16500)
        # Act
        mv = fast_manager.portfolio_market_value(aid)
        # Assert
        assert mv == 10 * 29000 + 5 * 16500

    def test_portfolio_market_value_emptyAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: account with no holdings. Act: portfolio_market_value. Assert: 0."""
        # Arrange
        aid = fast_manager.add_account("Empty", 1, account_subtype="brokerage")
        # Act & Assert
        assert fast_manager.portfolio_market_value(aid) == 0

    def test_portfolio_market_value_nonexistentAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: no account. Act: portfolio_market_value(99999). Assert: 0."""
        # Arrange & Act & Assert
        assert fast_manager.portfolio_market_value(99999) == 0

    def test_portfolio_market_value_partialPrices_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        """Arrange: two holdings, one missing price. Act: portfolio_market_value. Assert: None."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.set_holding(aid, "AAPL", 5.0, 75000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        # Act — AAPL has no price saved
        mv = fast_manager.portfolio_market_value(aid)
        # Assert
        assert mv is None
