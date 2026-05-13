"""Component tests: investment lifecycle.

Tests the orchestration of buy → hold → sell → gain/loss within the
AccountManager, verifying holdings, cash movement, and equation balance
at each step.

Boundary: all internal logic kept (Account + Journal + Ledger + Holding),
only DatabaseController is mocked (MockDB via fast_manager).
Black-box: tests through buy_security, sell_security, generate_ledger,
  check_accounting_equation, portfolio_market_value.
"""

import pytest
from datetime import datetime
from ledger.models.data_class import Split


class TestBuyHoldSellCycle:
    """Full investment lifecycle — buy, hold, sell with gain/loss."""

    def test_buy_hold_sell_gain(self, fast_manager):
        """Buy shares → hold → sell at higher price → realized gain booked.

        Buy: 10 VTI @ $275 = $2,750
        Sell: 10 VTI @ $290 = $2,900
        Gain: $150
        """
        m = fast_manager
        checking = m.add_account("Checking", 1)
        brokerage = m.add_account("Brokerage", 1, account_subtype="brokerage")
        gains = m.add_account("Gains", 4)

        # Fund the account
        m.add_transaction(datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(6, -10000000)])
        m.generate_ledger()

        # Buy: 10 VTI @ $275
        m.buy_security(datetime(2026, 2, 1), "Buy VTI",
            brokerage, checking, "VTI", 10, 27500)

        # Hold — verify state before selling
        m.generate_ledger()
        assert m.check_accounting_equation()["balanced"] is True
        holdings = m.get_holdings(brokerage)
        assert any(h.ticker == "VTI" for h in holdings)

        # Sell at a gain: 10 VTI @ $290
        m.sell_security(datetime(2026, 3, 1), "Sell VTI",
            brokerage, checking, "VTI", 10, 29000,
            gain_account_id=gains)

        m.generate_ledger()
        assert m.check_accounting_equation()["balanced"] is True

        # Verify gain was booked
        report = m.gen_income_report()
        assert report["income_total"] > 0, "Gain should appear as income"

        # Checking went up by sell proceeds
        m2 = fast_manager  # same reference
        # Checking should have initial $100K - $2,750 + $2,900 = $100,150
        # But the MockDB doesn't persist, so this is in the same manager
        checking_bal = m.get_display_balance(checking)
        expected_checking = 10000000 - (10 * 27500) + (10 * 29000)
        assert checking_bal == expected_checking, (
            f"Checking {checking_bal} != expected {expected_checking}"
        )

    def test_buy_hold_sell_loss(self, fast_manager):
        """Buy → sell at lower price → realized loss.

        Buy: 5 AAPL @ $150 = $750
        Sell: 5 AAPL @ $130 = $650
        Loss: -$100
        """
        m = fast_manager
        checking = m.add_account("Checking", 1)
        brokerage = m.add_account("Brokerage", 1, account_subtype="brokerage")
        losses = m.add_account("Losses", 5)  # expense account for losses

        m.add_transaction(datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(6, -10000000)])
        m.generate_ledger()

        m.buy_security(datetime(2026, 2, 1), "Buy AAPL",
            brokerage, checking, "AAPL", 5, 15000)
        m.generate_ledger()

        m.sell_security(datetime(2026, 3, 1), "Sell AAPL",
            brokerage, checking, "AAPL", 5, 13000,
            gain_account_id=losses)
        m.generate_ledger()

        assert m.check_accounting_equation()["balanced"] is True

        # Loss appears as expense
        report = m.gen_income_report()
        assert report["expenses_total"] > 0, "Loss should appear as expense"

    def test_buy_twice_avg_cost(self, fast_manager):
        """Two buys at different prices → average cost basis computed correctly.

        Buy 1: 10 @ $200 = $2,000
        Buy 2: 10 @ $300 = $3,000
        Avg cost: $250
        Sell at $280 → gain of $30/share = $300
        """
        m = fast_manager
        checking = m.add_account("Checking", 1)
        brokerage = m.add_account("Brokerage", 1, account_subtype="brokerage")
        gains = m.add_account("Gains", 4)

        m.add_transaction(datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(6, -10000000)])
        m.generate_ledger()

        m.buy_security(datetime(2026, 2, 1), "Buy 1",
            brokerage, checking, "XYZ", 10, 20000)
        m.buy_security(datetime(2026, 3, 1), "Buy 2",
            brokerage, checking, "XYZ", 10, 30000)
        m.generate_ledger()
        assert m.check_accounting_equation()["balanced"] is True

        # Sell 10 shares @ $280 (avg cost $250)
        m.sell_security(datetime(2026, 4, 1), "Sell",
            brokerage, checking, "XYZ", 10, 28000,
            gain_account_id=gains)
        m.generate_ledger()
        assert m.check_accounting_equation()["balanced"] is True

        # Gain should be 10 × ($280 - $250) = $300
        report = m.gen_income_report()
        assert report["income_total"] == 30000, (
            f"Expected $300 gain, got {report['income_total']}"
        )

    def test_portfolio_value_tracks_prices(self, fast_manager):
        """Portfolio market value reflects latest prices after buys."""
        m = fast_manager
        checking = m.add_account("Checking", 1)
        brokerage = m.add_account("Brokerage", 1, account_subtype="brokerage")

        m.add_transaction(datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(6, -10000000)])
        m.generate_ledger()

        m.buy_security(datetime(2026, 2, 1), "Buy VTI",
            brokerage, checking, "VTI", 40, 27500)
        m.buy_security(datetime(2026, 3, 1), "Buy AAPL",
            brokerage, checking, "AAPL", 20, 15000)
        m.generate_ledger()

        m.save_price("VTI", "2026-05-13", 29000)
        m.save_price("AAPL", "2026-05-13", 16500)

        mv = m.portfolio_market_value(brokerage)
        expected = 40 * 29000 + 20 * 16500
        assert mv == expected, (
            f"Market value {mv} != expected {expected}"
        )

    def test_sell_all_then_buy_back(self, fast_manager):
        """Sell entire position → buy again → new cost basis.

        Buy 10 @ $100, sell all 10, buy 5 @ $120.
        Second position should have $120 avg cost, not average of both.
        """
        m = fast_manager
        checking = m.add_account("Checking", 1)
        brokerage = m.add_account("Brokerage", 1, account_subtype="brokerage")
        gains = m.add_account("Gains", 4)

        m.add_transaction(datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(6, -10000000)])
        m.generate_ledger()

        m.buy_security(datetime(2026, 2, 1), "Buy",
            brokerage, checking, "TICK", 10, 10000)
        m.generate_ledger()

        m.sell_security(datetime(2026, 3, 1), "Sell all",
            brokerage, checking, "TICK", 10, 11000,
            gain_account_id=gains)
        m.generate_ledger()

        # Buy back at different price
        m.buy_security(datetime(2026, 4, 1), "Buy back",
            brokerage, checking, "TICK", 5, 12000)
        m.generate_ledger()

        assert m.check_accounting_equation()["balanced"] is True
        # New position should be 5 shares @ $120 avg cost
        from ledger.controllers.accounts import AccountManager
        avg = m._avg_cost_basis(brokerage, "TICK")
        assert avg == 12000, f"Avg cost {avg} != 12000"
