"""Unit tests: buy/sell security transactions, cost basis, gains/losses."""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


class TestBuySecurity:
    """Buying securities: position tracking, cost basis, journal entries."""

    def test_buy_creates_holding(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 100000), Split(6, -100000)],
        )
        txn_id = manager.buy_security(
            datetime(2026, 1, 15), "Buy VTI",
            brokerage, checking, "VTI", 10.0, 27500,
        )
        h = manager.get_holdings(brokerage)
        assert len(h) == 1
        assert h[0].ticker == "VTI"
        assert h[0].shares == 10.0
        assert h[0].cost_basis_cents == 275000

    def test_buy_updates_cash_and_brokerage(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 500000), Split(brokerage, 100000),
             Split(6, -600000)],
        )
        manager.buy_security(
            datetime(2026, 1, 15), "Buy VTI",
            brokerage, checking, "VTI", 10.0, 27500,
        )
        manager.generate_ledger()
        assert manager.get_display_balance(checking) == 500000 - 275000
        assert manager.get_display_balance(brokerage) == 100000 + 275000

    def test_buy_average_cost(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 1000000), Split(brokerage, 500000),
             Split(6, -1500000)],
        )
        # Buy 10 @ $275
        manager.buy_security(datetime(2026, 2, 1), "Batch 1",
                             brokerage, checking, "VTI", 10, 27500)
        # Buy 5 @ $280
        manager.buy_security(datetime(2026, 3, 1), "Batch 2",
                             brokerage, checking, "VTI", 5, 28000)
        h = manager.get_holdings(brokerage)[0]
        assert h.shares == 15.0
        assert h.cost_basis_cents == 275000 + 140000

    def test_buy_fractional_shares(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 500000), Split(brokerage, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(
            datetime(2026, 2, 1), "Buy MESP fund",
            brokerage, checking, "MESP-MD-R1", 10.543, 10500,
        )
        h = manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 10.543) < 0.001

    def test_buy_invalid_account_raises(self, manager: AccountManager):
        with pytest.raises(ValueError, match="Invalid account"):
            manager.buy_security(
                datetime(2026, 1, 1), "Bad",
                99999, 2, "VTI", 10, 10000,
            )

    def test_buy_zero_shares_raises(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1)
        with pytest.raises(ValueError, match="Shares must be positive"):
            manager.buy_security(
                datetime(2026, 1, 1), "Bad",
                brokerage, checking, "VTI", 0, 10000,
            )


class TestSellSecurity:
    """Selling securities: position reduction, gain/loss calculation."""

    def test_sell_reduces_holding(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy",
                             brokerage, checking, "VTI", 10, 27500)
        txn_id, realized = manager.sell_security(
            datetime(2026, 3, 1), "Sell",
            brokerage, checking, "VTI", 5, 29500,
        )
        h = manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 5.0) < 0.001
        assert realized > 0

    def test_sell_full_exit(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy",
                             brokerage, checking, "VTI", 10, 27500)
        manager.sell_security(datetime(2026, 3, 1), "Sell All",
                              brokerage, checking, "VTI", 10, 29500)
        assert len(manager.get_holdings(brokerage)) == 0

    def test_sell_with_gain_account(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        gain_acct = manager.add_account("Cap Gains", 4)
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy",
                             brokerage, checking, "VTI", 10, 27500)
        txn_id, realized = manager.sell_security(
            datetime(2026, 3, 1), "Sell",
            brokerage, checking, "VTI", 5, 29500,
            gain_account_id=gain_acct,
        )
        manager.generate_ledger()
        gain_bal = manager.get_display_balance(gain_acct)
        assert gain_bal > 0
        assert abs(gain_bal - realized) < 2  # allow rounding

    def test_sell_not_enough_shares_raises(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1)
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy",
                             brokerage, checking, "VTI", 5, 27500)
        with pytest.raises(ValueError, match="Cannot sell|only"):
            manager.sell_security(datetime(2026, 3, 1), "Sell Too Many",
                                  brokerage, checking, "VTI", 10, 29500)

    def test_sell_no_position_raises(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1)
        with pytest.raises(ValueError, match="No position"):
            manager.sell_security(datetime(2026, 1, 1), "Sell",
                                  brokerage, checking, "VTI", 5, 10000)

    def test_sell_with_realized_loss(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        loss_acct = manager.add_account("Trading Losses", 5)  # Expense
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy High",
                             brokerage, checking, "VTI", 10, 30000)
        txn_id, realized = manager.sell_security(
            datetime(2026, 3, 1), "Sell Low",
            brokerage, checking, "VTI", 10, 28000,
            gain_account_id=loss_acct,
        )
        manager.generate_ledger()
        assert realized < 0  # Should be a loss

    def test_average_cost_basis(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 1000000), Split(checking, 1000000),
             Split(6, -2000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy @ 100",
                             brokerage, checking, "VTI", 10, 10000)
        manager.buy_security(datetime(2026, 3, 1), "Buy @ 200",
                             brokerage, checking, "VTI", 5, 20000)
        # Avg cost = (10*10000 + 5*20000) / 15 = 200000/15 = 13333.33
        avg = manager._avg_cost_basis(brokerage, "VTI")
        assert abs(avg - 13333.33) < 1

    def test_buy_sell_keeps_equation_balanced(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        gain = manager.add_account("Cap Gains", 4)
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 1000000), Split(checking, 1000000),
             Split(6, -2000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy",
                             brokerage, checking, "VTI", 10, 27500)
        manager.sell_security(datetime(2026, 3, 1), "Sell Half",
                              brokerage, checking, "VTI", 5, 29500,
                              gain_account_id=gain)
        manager.generate_ledger()
        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, (
            f"Equation unbalanced after trades: "
            f"A={eq['assets']}, L={eq['liabilities']}, E={eq['equity']}+NI={eq['net_income']}"
        )


class TestAvgCostBasis:
    """Average-cost-basis helper calculations."""

    def test_avg_cost_single_buy(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 10.0, 275000)
        assert manager._avg_cost_basis(aid, "VTI") == 27500.0

    def test_avg_cost_no_holding(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        assert manager._avg_cost_basis(aid, "VTI") == 0.0

    def test_avg_cost_zero_shares(self, manager: AccountManager):
        aid = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.set_holding(aid, "VTI", 0.0, 0)
        assert manager._avg_cost_basis(aid, "VTI") == 0.0
