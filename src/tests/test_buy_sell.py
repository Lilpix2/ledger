"""Unit tests: buy/sell security transactions, cost basis, gains/losses.

All tests use ``fast_manager`` (MockDB, zero disk I/O).
AAA pattern enforced throughout.
"""

import pytest
from datetime import datetime

from ledger.models.data_class import Split


# ═══════════════════════════════════════════════════════════════════
# BuySecurity
# ═══════════════════════════════════════════════════════════════════

class TestBuySecurity:
    """Buying securities: position tracking, cost basis, journal entries."""

    # ── Happy path ────────────────────────────────────────────────

    def test_buySecurity_createsHolding(self, fast_manager):
        """Arrange: checking + brokerage. Act: buy 10 VTI @ $275.
        Assert: holding created with correct ticker/shares/cost."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")

        # Act
        fast_manager.buy_security(
            datetime(2026, 1, 15), "Buy VTI", brokerage, checking, "VTI", 10.0, 27500,
        )

        # Assert
        h = fast_manager.get_holdings(brokerage)
        assert len(h) == 1
        assert h[0].ticker == "VTI"
        assert h[0].shares == 10.0
        assert h[0].cost_basis_cents == 275000

    def test_buySecurity_updatesCashAndBrokerage(self, fast_manager):
        """Arrange: accounts + initial balances. Act: buy 10 VTI @ $275.
        Assert: cash decreases, brokerage increases."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # Fund the accounts via retained earnings (account 6 = ret. earnings in MockDB)
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 500000), Split(brokerage, 100000),
             Split(6, -600000)],
        )

        # Act
        fast_manager.buy_security(
            datetime(2026, 1, 15), "Buy VTI", brokerage, checking, "VTI", 10.0, 27500,
        )
        fast_manager.generate_ledger()

        # Assert
        assert fast_manager.get_display_balance(checking) == 500000 - 275000
        assert fast_manager.get_display_balance(brokerage) == 100000 + 275000

    # ── Average cost ──────────────────────────────────────────────

    def test_buySecurity_averageCost_twoBuys(self, fast_manager):
        """Arrange: funded accounts. Act: two buys at different prices.
        Assert: shares sum, cost basis sums."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 1000000), Split(brokerage, 500000),
             Split(6, -1500000)],
        )

        # Act — Batch 1: 10 @ $275, Batch 2: 5 @ $280
        fast_manager.buy_security(datetime(2026, 2, 1), "Batch 1",
                                  brokerage, checking, "VTI", 10, 27500)
        fast_manager.buy_security(datetime(2026, 3, 1), "Batch 2",
                                  brokerage, checking, "VTI", 5, 28000)

        # Assert
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 15.0
        assert h.cost_basis_cents == 275000 + 140000

    # ── Fractional shares ─────────────────────────────────────────

    def test_buySecurity_fractionalShares_stored(self, fast_manager):
        """Arrange: funded accounts. Act: buy 10.543 shares.
        Assert: shares stored within 0.001 tolerance."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 500000), Split(brokerage, 500000),
             Split(6, -1000000)],
        )

        # Act
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Buy fractional",
            brokerage, checking, "MESP-MD-R1", 10.543, 10500,
        )

        # Assert
        h = fast_manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 10.543) < 0.001

    def test_buySecurity_oneShare_works(self, fast_manager):
        """Arrange: funded accounts. Act: buy 1 share. Assert: holding created."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 100000), Split(6, -100000)],
        )

        # Act
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Buy 1", brokerage, checking, "AAPL", 1.0, 15000,
        )

        # Assert
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 1.0
        assert h.cost_basis_cents == 15000

    # ── Edge cases ────────────────────────────────────────────────

    def test_buySecurity_invalidBrokerageAccount_raises(self, fast_manager):
        """Arrange: only checking account. Act: buy on nonexistent brokerage.
        Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Bad", 99999, checking, "VTI", 10, 10000,
            )

    def test_buySecurity_invalidCashAccount_raises(self, fast_manager):
        """Arrange: only brokerage account. Act: buy with nonexistent cash acct.
        Assert: ValueError."""
        # Arrange
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Bad", brokerage, 99999, "VTI", 10, 10000,
            )

    def test_buySecurity_zeroShares_raises(self, fast_manager):
        """Arrange: two accounts. Act: buy 0 shares. Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Bad", brokerage, checking, "VTI", 0, 10000,
            )

    def test_buySecurity_negativeShares_raises(self, fast_manager):
        """Arrange: accounts. Act: buy -5 shares. Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)

        # Act & Assert
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Bad", brokerage, checking, "VTI", -5, 10000,
            )

    def test_buySecurity_zeroPriceCents_raises(self, fast_manager):
        """Arrange: accounts. Act: buy at $0/unit (total = 0). Assert: ValueError
        (total cost non-zero check)."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)

        # Act & Assert
        with pytest.raises((ValueError, ZeroDivisionError)):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Free", brokerage, checking, "VTI", 10, 0,
            )


# ═══════════════════════════════════════════════════════════════════
# SellSecurity
# ═══════════════════════════════════════════════════════════════════

class TestSellSecurity:
    """Selling securities: position reduction, gain/loss calculation."""

    def _fund_and_buy(self, mgr, ticker="VTI", shares=10, price=27500):
        """Helper: fund accounts and buy shares. Returns (checking_id, brokerage_id)."""
        checking = mgr.add_account("Checking", 1)
        brokerage = mgr.add_account("Brokerage", 1, account_subtype="brokerage")
        mgr.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        mgr.buy_security(datetime(2026, 2, 1), f"Buy {ticker}",
                         brokerage, checking, ticker, shares, price)
        return checking, brokerage

    # ── Happy path ────────────────────────────────────────────────

    def test_sellSecurity_reducesHolding(self, fast_manager):
        """Arrange: buy 10 VTI. Act: sell 5. Assert: holding has 5 remaining,
        realized gain > 0."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 27500)

        # Act
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell", brokerage, checking, "VTI", 5, 29500,
        )

        # Assert
        h = fast_manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 5.0) < 0.001
        assert realized > 0

    def test_sellSecurity_fullExit_removesHolding(self, fast_manager):
        """Arrange: buy 10 VTI. Act: sell all 10. Assert: no holdings left."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 27500)

        # Act
        fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell All", brokerage, checking, "VTI", 10, 29500,
        )

        # Assert
        assert len(fast_manager.get_holdings(brokerage)) == 0

    def test_sellSecurity_withGainAccount_booksGain(self, fast_manager):
        """Arrange: buy + gain account. Act: sell with gain_account_id.
        Assert: gain account balance > 0 and matches realized."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 27500)
        gain_acct = fast_manager.add_account("Cap Gains", 4)

        # Act
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell", brokerage, checking, "VTI", 5, 29500,
            gain_account_id=gain_acct,
        )
        fast_manager.generate_ledger()

        # Assert
        gain_bal = fast_manager.get_display_balance(gain_acct)
        assert gain_bal > 0
        assert abs(gain_bal - realized) < 2  # allow rounding

    def test_sellSecurity_withLossAccount_booksLoss(self, fast_manager):
        """Arrange: buy high, sell low. Act: sell with gain_account_id (loss acct).
        Assert: realized loss is negative."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 30000)
        loss_acct = fast_manager.add_account("Trading Losses", 5)

        # Act
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell Low", brokerage, checking, "VTI", 10, 28000,
            gain_account_id=loss_acct,
        )
        fast_manager.generate_ledger()

        # Assert
        assert realized < 0

    def test_sellSecurity_partial_keepsEquationBalanced(self, fast_manager):
        """Arrange: buy + gain acct. Act: sell half. Assert: accounting eq balanced."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 27500)
        gain = fast_manager.add_account("Cap Gains", 4)

        # Act
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy",
                                  brokerage, checking, "VTI", 10, 27500)
        fast_manager.sell_security(datetime(2026, 3, 1), "Sell Half",
                                   brokerage, checking, "VTI", 5, 29500,
                                   gain_account_id=gain)
        fast_manager.generate_ledger()

        # Assert
        eq = fast_manager.check_accounting_equation()
        assert eq["balanced"] is True, (
            f"Equation unbalanced after trades: "
            f"A={eq['assets']}, L={eq['liabilities']}, E={eq['equity']}+NI={eq['net_income']}"
        )

    # ── Edge cases ────────────────────────────────────────────────

    def test_sellSecurity_notEnoughShares_raises(self, fast_manager):
        """Arrange: buy 5 shares. Act: sell 10. Assert: ValueError."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 5, 27500)

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot sell|only"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Sell Too Many",
                brokerage, checking, "VTI", 10, 29500,
            )

    def test_sellSecurity_noPosition_raises(self, fast_manager):
        """Arrange: funded accounts, no purchase. Act: sell. Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)

        # Act & Assert
        with pytest.raises(ValueError, match="No position"):
            fast_manager.sell_security(
                datetime(2026, 1, 1), "Sell", brokerage, checking, "VTI", 5, 10000,
            )

    def test_sellSecurity_zeroShares_raises(self, fast_manager):
        """Arrange: buy shares. Act: sell 0 shares. Assert: ValueError."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 27500)

        # Act & Assert
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Zero", brokerage, checking, "VTI", 0, 29500,
            )

    def test_sellSecurity_negativeShares_raises(self, fast_manager):
        """Arrange: buy shares. Act: sell -5. Assert: ValueError."""
        # Arrange
        checking, brokerage = self._fund_and_buy(fast_manager, "VTI", 10, 27500)

        # Act & Assert
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Bad", brokerage, checking, "VTI", -5, 29500,
            )

    def test_sellSecurity_invalidBrokerage_raises(self, fast_manager):
        """Arrange: no brokerage account. Act: sell with bad brokerage ID.
        Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.sell_security(
                datetime(2026, 1, 1), "Bad", 99999, checking, "VTI", 5, 10000,
            )


# ═══════════════════════════════════════════════════════════════════
# AvgCostBasis
# ═══════════════════════════════════════════════════════════════════

class TestAvgCostBasis:
    """Average-cost-basis helper calculations."""

    def test_avgCost_singleBuy_returnsPrice(self, fast_manager):
        """Arrange: holding with 10 shares @ $275. Assert: avg = 27500."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)

        # Act & Assert
        assert fast_manager._avg_cost_basis(aid, "VTI") == 27500.0

    def test_avgCost_noHolding_returnsZero(self, fast_manager):
        """Arrange: no holding set. Assert: _avg_cost_basis returns 0."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")

        # Act & Assert
        assert fast_manager._avg_cost_basis(aid, "VTI") == 0.0

    def test_avgCost_zeroShares_returnsZero(self, fast_manager):
        """Arrange: holding with 0 shares. Assert: returns 0 (avoid div/0)."""
        # Arrange
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 0.0, 0)

        # Act & Assert
        assert fast_manager._avg_cost_basis(aid, "VTI") == 0.0

    def test_avgCost_nonexistentAccount_returnsZero(self, fast_manager):
        """Arrange: no brokerage account at all. Assert: returns 0."""
        # Act & Assert
        assert fast_manager._avg_cost_basis(99999, "VTI") == 0.0

    def test_avgCost_twoBuys_computedCorrectly(self, fast_manager):
        """Arrange: two buys at different prices. Assert: avg = total_cost / total_shares."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 1000000), Split(checking, 1000000),
             Split(6, -2000000)],
        )
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy @ 100",
                                  brokerage, checking, "VTI", 10, 10000)
        fast_manager.buy_security(datetime(2026, 3, 1), "Buy @ 200",
                                  brokerage, checking, "VTI", 5, 20000)

        # Avg cost = (10*10000 + 5*20000) / (10+5) = 200000/15 = 13333.33...
        # Act & Assert
        avg = fast_manager._avg_cost_basis(brokerage, "VTI")
        assert abs(avg - 13333.33) < 1
