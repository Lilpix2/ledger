"""Integration tests: database persistence, full accounting cycles, investment lifecycle.

These tests verify that the system behaves correctly across component
boundaries — database persistence, ledger regeneration, and the
end-to-end accounting cycle.
"""

import pytest
import tempfile
import os
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split, JournalTransaction


# ═══════════════════════════════════════════════════════════════════
#  Database Persistence  (reopen same DB file)
# ═══════════════════════════════════════════════════════════════════


class TestDatabasePersistence:
    """Transactions and accounts survive a close/reopen cycle."""

    @pytest.fixture
    def db_path(self) -> str:
        path = tempfile.mktemp(suffix=".db")
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_transaction_persistence(self, db_path: str):
        """Add a transaction, close manager, reopen, verify it exists."""
        # ── First session ──
        mgr1 = AccountManager(db_path)
        checking = mgr1.add_account("Checking", 1)
        groceries = mgr1.add_account("Groceries", 5)

        txn_id = mgr1.add_transaction(
            datetime(2026, 1, 15), "Weekly shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        assert txn_id >= 0
        del mgr1  # close

        # ── Second session ──
        mgr2 = AccountManager(db_path)
        # Transaction should be loaded from DB
        assert len(mgr2.journal.transactions) >= 1
        # Find the transaction by checking description
        found = False
        for txn in mgr2.journal.transactions.values():
            if txn.description == "Weekly shop":
                found = True
                assert len(txn.splits) == 2
                break
        assert found, "Transaction not found after reopen"

        mgr2.generate_ledger()
        # Find accounts by name
        for aid, acct in mgr2.accounts.items():
            if acct.name == "Checking":
                assert acct.get_balance() == -5000
                break
        else:
            pytest.fail("Checking account not found after reopen")

    def test_account_persistence(self, db_path: str):
        """Add accounts, reopen, verify they exist with correct attributes."""
        # ── First session ──
        mgr1 = AccountManager(db_path)
        aid = mgr1.add_account("My Savings", 1, account_subtype="checking")
        assert mgr1.accounts[aid].name == "My Savings"
        assert mgr1.accounts[aid].account_subtype == "checking"
        del mgr1

        # ── Second session ──
        mgr2 = AccountManager(db_path)
        assert aid in mgr2.accounts
        assert mgr2.accounts[aid].name == "My Savings"
        assert mgr2.accounts[aid].account_subtype == "checking"

    def test_delete_transaction_persistence(self, db_path: str):
        """Delete a transaction, reopen, verify it's gone."""
        # ── First session ──
        mgr1 = AccountManager(db_path)
        checking = mgr1.add_account("Checking", 1)
        groceries = mgr1.add_account("Groceries", 5)

        txn_id = mgr1.add_transaction(
            datetime(2026, 1, 15), "Will be deleted",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        mgr1.delete_transaction(txn_id)
        del mgr1

        # ── Second session ──
        mgr2 = AccountManager(db_path)
        # The deleted transaction should NOT be in the journal
        for txn in mgr2.journal.transactions.values():
            assert txn.description != "Will be deleted", (
                "Deleted transaction should not persist"
            )

    def test_holding_persistence(self, db_path: str):
        """Holdings survive a close/reopen cycle."""
        # ── First session ──
        mgr1 = AccountManager(db_path)
        brokerage = mgr1.add_account("Brokerage", 1, account_subtype="brokerage")
        mgr1.set_holding(brokerage, "VTI", 100.0, 2750000)
        del mgr1

        # ── Second session ──
        mgr2 = AccountManager(db_path)
        holdings = mgr2.get_holdings(brokerage)
        assert len(holdings) == 1
        assert holdings[0].ticker == "VTI"
        assert holdings[0].shares == 100.0
        assert holdings[0].cost_basis_cents == 2750000

    def test_price_persistence(self, db_path: str):
        """Price quotes survive a close/reopen cycle."""
        # ── First session ──
        mgr1 = AccountManager(db_path)
        mgr1.save_price("VT", "2026-05-13", 11000)
        del mgr1

        # ── Second session ──
        mgr2 = AccountManager(db_path)
        price = mgr2.get_price("VT", "2026-05-13")
        assert price == 11000

    def test_multiple_transactions_persistence(self, db_path: str):
        """Multiple transactions all survive a reopen cycle."""
        mgr1 = AccountManager(db_path)
        checking = mgr1.add_account("Checking", 1)
        salary = mgr1.add_account("Salary", 4)
        rent = mgr1.add_account("Rent", 5)
        food = mgr1.add_account("Food", 5)

        mgr1.add_transaction(
            datetime(2026, 1, 1), "Payday",
            [Split(salary, -200000), Split(checking, 200000)],
        )
        mgr1.add_transaction(
            datetime(2026, 1, 2), "Rent",
            [Split(rent, 50000), Split(checking, -50000)],
        )
        mgr1.add_transaction(
            datetime(2026, 1, 3), "Groceries",
            [Split(food, 15000), Split(checking, -15000)],
        )
        del mgr1

        mgr2 = AccountManager(db_path)
        descriptions = {t.description for t in mgr2.journal.transactions.values()}
        assert "Payday" in descriptions
        assert "Rent" in descriptions
        assert "Groceries" in descriptions
        assert len(descriptions) == 3


# ═══════════════════════════════════════════════════════════════════
#  Full Accounting Cycle
# ═══════════════════════════════════════════════════════════════════


class TestFullAccountingCycle:
    """End-to-end: accounts → transactions → ledger → reports → close temps."""

    def test_full_cycle(self, manager: AccountManager):
        """Add accounts → add transactions → generate ledger → run reports
        → close temporary accounts → verify temps zeroed and RE updated."""
        # ── Setup: create income, expense, and cash accounts ──
        checking = manager.add_account("Checking", 1)
        salary = manager.add_account("Salary", 4)
        groceries = manager.add_account("Groceries", 5)
        utilities = manager.add_account("Utilities", 5)

        # ── Add transactions ──
        manager.add_transaction(
            datetime(2026, 1, 1), "January Paycheck",
            [Split(salary, -300000), Split(checking, 300000)],
        )
        manager.add_transaction(
            datetime(2026, 1, 5), "Groceries",
            [Split(groceries, 45000), Split(checking, -45000)],
        )
        manager.add_transaction(
            datetime(2026, 1, 10), "Electric Bill",
            [Split(utilities, 12000), Split(checking, -12000)],
        )
        manager.add_transaction(
            datetime(2026, 2, 1), "February Paycheck",
            [Split(salary, -300000), Split(checking, 300000)],
        )
        manager.add_transaction(
            datetime(2026, 2, 5), "Groceries Feb",
            [Split(groceries, 50000), Split(checking, -50000)],
        )

        # ── Generate ledger ──
        manager.generate_ledger()

        # ── Verify balances before close ──
        assert manager.accounts[checking].get_balance() == 493000  # 600K - 45K - 12K - 50K
        assert manager.accounts[salary].get_balance() == -600000   # credit-normal income
        assert manager.accounts[groceries].get_balance() == 95000  # debit-normal expense
        assert manager.accounts[utilities].get_balance() == 12000

        # ── Run reports ──
        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, "Equation must balance"

        income_report = manager.gen_income_report()
        assert income_report["income_total"] == 600000
        assert income_report["expenses_total"] == 107000  # 45000 + 12000 + 50000
        assert income_report["net_income"] == 493000

        re_stmt = manager.gen_retained_earnings_statement()
        net_income = income_report["net_income"]
        assert re_stmt["net_income"] == net_income

        bs = manager.gen_balance_sheet()
        assert bs["balanced"] is True

        summary = manager.gen_account_summary()
        assert summary["balanced"] is True

        # ── Get RE balance before closing ──
        re_before = manager.accounts[6].get_balance()  # retained earnings (credit-normal)

        # ── Close temporary accounts ──
        manager.close_temps()
        manager.generate_ledger()

        # ── Verify income/expense accounts are reset to zero ──
        assert manager.accounts[salary].get_balance() == 0, "Income should be closed to zero"
        assert manager.accounts[groceries].get_balance() == 0, "Expense should be closed to zero"
        assert manager.accounts[utilities].get_balance() == 0, "Expense should be closed to zero"

        # ── Verify Retained Earnings updated ──
        # RE is credit-normal: raw balance goes more negative
        re_after = manager.accounts[6].get_balance()
        re_change = -(re_after - re_before)  # flip to display-normal
        assert re_change == net_income, (
            f"RE should increase by net income ({net_income}), "
            f"got {re_change}"
        )

        # ── Verify accounting equation still balances ──
        eq_after = manager.check_accounting_equation()
        assert eq_after["balanced"] is True, (
            "Equation must balance after closing temps"
        )

        # ── Checking account should be unchanged (real account) ──
        assert manager.accounts[checking].get_balance() == 493000


# ═══════════════════════════════════════════════════════════════════
#  Investment Lifecycle
# ═══════════════════════════════════════════════════════════════════


class TestInvestmentLifecycle:
    """Buy → hold → sell partial → sell rest → verify equation stays balanced."""

    def test_buy_hold_sell_cycle(self, manager: AccountManager):
        """Full investment lifecycle: buy → verify → sell partial → verify
        → sell rest → verify holdings empty and equation balanced."""
        # ── Setup ──
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        gain_acct = manager.add_account("Cap Gains", 4)

        # Fund the accounts with initial cash
        manager.add_transaction(
            datetime(2026, 1, 1), "Initial funding",
            [Split(brokerage, 500000), Split(checking, 1000000),
             Split(6, -1500000)],
        )
        manager.generate_ledger()

        # ── Step 1: Buy a security ──
        txn_id = manager.buy_security(
            datetime(2026, 2, 1), "Buy AAPL",
            brokerage, checking, "AAPL", 20, 15000,  # 20 × $150 = $3,000
        )
        manager.generate_ledger()
        assert txn_id >= 0

        # ── Verify holdings after buy ──
        holdings = manager.get_holdings(brokerage)
        assert len(holdings) == 1
        assert holdings[0].ticker == "AAPL"
        assert holdings[0].shares == 20.0
        assert holdings[0].cost_basis_cents == 300000  # 20 × 15000

        # ── Verify balances after buy ──
        # Checking: 1,000,000 - 300,000 = 700,000
        assert manager.accounts[checking].get_balance() == 700000
        # Brokerage: 500,000 + 300,000 = 800,000
        assert manager.accounts[brokerage].get_balance() == 800000

        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, "Equation must balance after buy"

        # ── Step 2: Sell partial position ──
        sell_txn_id, realized_gain = manager.sell_security(
            datetime(2026, 3, 1), "Sell half AAPL",
            brokerage, checking, "AAPL", 10, 17000,  # 10 × $170 = $1,700
            gain_account_id=gain_acct,
        )
        manager.generate_ledger()
        assert sell_txn_id >= 0

        # Cost of sold shares: 10 × ($300,000 / 20) = 10 × $15,000 = $150,000
        # Proceeds: 10 × $17,000 = $170,000
        # Realized gain: $170,000 - $150,000 = $20,000
        assert realized_gain == 20000, f"Expected gain of 20000, got {realized_gain}"

        # ── Verify holdings reduced ──
        holdings = manager.get_holdings(brokerage)
        assert len(holdings) == 1
        assert abs(holdings[0].shares - 10.0) < 0.001
        assert holdings[0].cost_basis_cents == 150000  # remaining shares × avg cost

        # ── Verify balances after partial sell ──
        # Checking: 700,000 + 170,000 = 870,000
        assert manager.accounts[checking].get_balance() == 870000
        # Brokerage: 800,000 - 150,000 = 650,000
        assert manager.accounts[brokerage].get_balance() == 650000

        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, "Equation must balance after partial sell"

        # ── Step 3: Sell remaining shares ──
        sell_txn_id2, realized_gain2 = manager.sell_security(
            datetime(2026, 4, 1), "Sell rest AAPL",
            brokerage, checking, "AAPL", 10, 18000,  # 10 × $180 = $1,800
            gain_account_id=gain_acct,
        )
        manager.generate_ledger()

        # Cost: 10 × $15,000 = $150,000
        # Proceeds: 10 × $18,000 = $180,000
        # Realized gain: $30,000
        assert realized_gain2 == 30000, f"Expected gain of 30000, got {realized_gain2}"

        # ── Verify holdings empty ──
        holdings = manager.get_holdings(brokerage)
        assert len(holdings) == 0, "Holdings should be empty after full exit"

        # ── Verify balances after full exit ──
        # Checking: 870,000 + 180,000 = 1,050,000
        assert manager.accounts[checking].get_balance() == 1050000
        # Brokerage: 650,000 - 150,000 = 500,000 (original funding remained)
        assert manager.accounts[brokerage].get_balance() == 500000

        # ── Verify accounting equation stays balanced ──
        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, (
            f"Equation unbalanced after full sell cycle: "
            f"A={eq['assets']}, L={eq['liabilities']}, "
            f"E={eq['equity']}+NI={eq['net_income']}"
        )

        # ── Verify total realized gains ──
        total_gain = realized_gain + realized_gain2
        assert total_gain == 50000, f"Expected total gain of 50000, got {total_gain}"
        # Capital Gains (income) account should show total gain
        assert manager.get_display_balance(gain_acct) == total_gain

    def test_buy_sell_maintains_equation(self, manager: AccountManager):
        """Extensive buy/sell sequence with multiple tickers."""
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        gain = manager.add_account("Cap Gains", 4)

        # Fund
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 1000000), Split(checking, 2000000),
             Split(6, -3000000)],
        )

        # Buy VTI and AAPL
        manager.buy_security(datetime(2026, 2, 1), "Buy VTI",
                             brokerage, checking, "VTI", 50, 27500)
        manager.buy_security(datetime(2026, 3, 1), "Buy AAPL",
                             brokerage, checking, "AAPL", 30, 15000)
        manager.generate_ledger()

        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, "Balanced after buys"

        # Sell VTI with gain, AAPL at loss
        manager.sell_security(datetime(2026, 4, 1), "Sell VTI",
                              brokerage, checking, "VTI", 25, 30000,
                              gain_account_id=gain)
        manager.sell_security(datetime(2026, 5, 1), "Sell AAPL",
                              brokerage, checking, "AAPL", 30, 14000,
                              gain_account_id=gain)
        manager.generate_ledger()

        eq = manager.check_accounting_equation()
        assert eq["balanced"] is True, (
            f"Equation unbalanced after sell cycle: "
            f"A={eq['assets']}, L={eq['liabilities']}, "
            f"E={eq['equity']}+NI={eq['net_income']}"
        )


# ═══════════════════════════════════════════════════════════════════
#  Delete Account — Persistence (delete with options)
# ═══════════════════════════════════════════════════════════════════


class TestDeleteAccountPersistence:
    """AccountManager delete/reassigned operations survive close/reopen."""

    @pytest.fixture
    def db_path(self) -> str:
        path = tempfile.mktemp(suffix=".db")
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def _seed(self, path: str):
        """Create a manager with accounts + transactions for delete tests."""
        mgr = AccountManager(path)
        parent = mgr.add_account("Parent", 1)
        child = mgr.add_account("Child", parent)
        source = mgr.add_account("Source", 1)
        target = mgr.add_account("Target", 1)
        equity = 6
        mgr.add_transaction(
            datetime(2026, 6, 1), "Fund Source",
            [Split(source, 100000), Split(equity, -100000)],
        )
        mgr.generate_ledger()
        return mgr, parent, child, source, target, equity

    # ── Simple delete — no children, no txns ────────────────

    def test_simple_delete_persists(self, db_path: str):
        """Delete a leaf account → gone on reopen."""
        mgr = AccountManager(db_path)
        acct = mgr.add_account("TempLeaf", 1)
        mgr.delete_account(acct)
        del mgr

        mgr2 = AccountManager(db_path)
        assert acct not in mgr2.accounts, "Deleted account should not persist"

    # ── Cascade delete — children ───────────────────────────

    def test_cascade_children_persists(self, db_path: str):
        """Delete parent cascades children → both gone on reopen."""
        mgr = AccountManager(db_path)
        parent = mgr.add_account("Parent", 1)
        child = mgr.add_account("Child", parent)
        mgr.delete_account(parent)
        del mgr

        mgr2 = AccountManager(db_path)
        assert parent not in mgr2.accounts
        assert child not in mgr2.accounts

    # ── Cascade delete — transactions ───────────────────────

    def test_cascade_transactions_persists(self, db_path: str):
        """Delete account cascades its transactions → both gone on reopen."""
        mgr = AccountManager(db_path)
        src = mgr.add_account("Src", 1)
        equity = 6
        mgr.add_transaction(
            datetime(2026, 6, 1), "Will cascade",
            [Split(src, 50000), Split(equity, -50000)],
        )
        mgr.generate_ledger()

        txn_count_before = len(mgr.journal.transactions)
        mgr.delete_account(src)
        del mgr

        mgr2 = AccountManager(db_path)
        remaining = len(mgr2.journal.transactions)
        assert remaining < txn_count_before, (
            f"Expected fewer transactions after cascade, got {remaining}"
        )
        for txn in mgr2.journal.transactions.values():
            assert txn.description != "Will cascade", "Cascaded txn survived reopen"

    # ── Reassign children ───────────────────────────────────

    def test_reassign_children_persists(self, db_path: str):
        """Children reparented → new parent persists on reopen."""
        mgr, parent, child, *_ = self._seed(db_path)
        new_parent = mgr.add_account("NewParent", 1)

        mgr.reassign_children(parent, new_parent)
        mgr.delete_account(parent)
        del mgr

        mgr2 = AccountManager(db_path)
        # Child should still exist and point to NewParent
        assert child in mgr2.accounts, "Child should persist"
        assert parent not in mgr2.accounts, "Old parent should be gone"
        assert mgr2.accounts[child].parent == new_parent, (
            f"Child parent={mgr2.accounts[child].parent}, expected {new_parent}"
        )

    def test_reassign_children_no_delete_persists(self, db_path: str):
        """Reparent alone persists even without deleting the old parent."""
        mgr, parent, child, *_ = self._seed(db_path)
        new_parent = mgr.add_account("NewParent", 1)

        mgr.reassign_children(parent, new_parent)
        del mgr

        mgr2 = AccountManager(db_path)
        assert mgr2.accounts[child].parent == new_parent, (
            "Child should point to new parent after reopen"
        )

    # ── Reassign transactions ───────────────────────────────

    def test_reassign_transactions_persists(self, db_path: str):
        """Splits migrated → balance moves to target on reopen."""
        mgr, parent, child, source, target, equity = self._seed(db_path)

        # Fund source with another txn
        mgr.add_transaction(
            datetime(2026, 6, 2), "Extra fund",
            [Split(source, 25000), Split(equity, -25000)],
        )
        mgr.generate_ledger()
        bal_before = mgr.get_display_balance(source)

        mgr.reassign_transactions(source, target)
        mgr.delete_account(source)
        del mgr

        mgr2 = AccountManager(db_path)
        assert source not in mgr2.accounts
        assert target in mgr2.accounts
        # Target should have the balance that source had
        assert mgr2.get_display_balance(target) == bal_before

    def test_reassign_transactions_no_delete_persists(self, db_path: str):
        """Reassign alone persists without deleting the source."""
        mgr, _, _, source, target, _ = self._seed(db_path)

        mgr.reassign_transactions(source, target)
        mgr.generate_ledger()
        source_bal = mgr.get_display_balance(source)
        del mgr

        mgr2 = AccountManager(db_path)
        # Source should still exist and have 0 balance (all splits migrated)
        assert source in mgr2.accounts
        assert mgr2.get_display_balance(source) == source_bal

    # ── Both reassigned then delete ─────────────────────────

    def test_both_reassigned_then_delete_persists(self, db_path: str):
        """Children reparented + txns migrated + source deleted → all persist."""
        mgr, parent, child, source, target, equity = self._seed(db_path)
        child_target = mgr.add_account("ChildTarget", 1)

        mgr.reassign_children(parent, child_target)
        mgr.reassign_transactions(source, target)
        mgr.generate_ledger()
        expected_txn_bal = mgr.get_display_balance(target)

        mgr.delete_account(parent)
        mgr.delete_account(source)
        del mgr

        mgr2 = AccountManager(db_path)
        # Children
        assert parent not in mgr2.accounts
        assert child in mgr2.accounts
        assert mgr2.accounts[child].parent == child_target
        # Transactions
        assert source not in mgr2.accounts
        assert target in mgr2.accounts
        assert mgr2.get_display_balance(target) == expected_txn_bal
        # Equation should balance
        mgr2.generate_ledger()
        eq = mgr2.check_accounting_equation()
        assert eq["balanced"], "Equation unbalanced after full reassign+delete"
