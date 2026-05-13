"""Unit tests: journal transactions, ledger integrity, trial balance."""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split, JournalTransaction, Holding, Price


class TestJournalTransactions:
    """Creating and validating compound journal entries."""

    def test_add_simple_transaction(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        txn_id = manager.add_transaction(
            datetime(2026, 1, 15), "Weekly shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        assert txn_id >= 0
        assert txn_id in manager.journal.transactions

    def test_add_compound_transaction(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        savings = manager.add_account("Savings", 1)
        salary = manager.add_account("Salary", 4)
        txn_id = manager.add_transaction(
            datetime(2026, 1, 15), "Payday split",
            [Split(salary, -200000), Split(checking, 150000),
             Split(savings, 50000)],
        )
        assert txn_id >= 0

    def test_unbalanced_transaction_raises(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        with pytest.raises(ValueError, match="Unbalanced"):
            manager.add_transaction(
                datetime(2026, 1, 15), "Bad",
                [Split(groceries, 5000), Split(checking, -4000)],
            )

    def test_empty_splits_raises(self, manager: AccountManager):
        with pytest.raises(ValueError, match="at least one split"):
            manager.add_transaction(datetime(2026, 1, 1), "Empty", [])

    def test_zero_amount_split_raises(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        with pytest.raises(ValueError, match="non-zero"):
            manager.add_transaction(
                datetime(2026, 1, 1), "Zero",
                [Split(groceries, 0), Split(checking, 100), Split(checking, -100)],
            )

    def test_nonexistent_account_raises(self, manager: AccountManager):
        with pytest.raises(ValueError, match="account"):
            manager.add_transaction(
                datetime(2026, 1, 1), "Bad",
                [Split(99999, 100), Split(2, -100)],
            )


class TestLedgerIntegrity:
    """Ledger generation, trial balance, chronological ordering."""

    def test_generate_ledger(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        salary = manager.add_account("Salary", 4)
        manager.add_transaction(
            datetime(2026, 1, 15), "Payday",
            [Split(salary, -200000), Split(checking, 200000)],
        )
        manager.add_transaction(
            datetime(2026, 1, 16), "Shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        manager.generate_ledger()
        assert manager.accounts[checking].get_balance() == 195000
        assert manager.accounts[groceries].get_balance() == 5000
        assert manager.accounts[salary].get_balance() == -200000

    def test_trial_balance(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        income = manager.add_account("Income", 4)
        expense = manager.add_account("Expense", 5)
        manager.add_transaction(
            datetime(2026, 1, 1), "Txn", [Split(income, -1000), Split(checking, 1000)],
        )
        manager.add_transaction(
            datetime(2026, 1, 2), "Txn", [Split(expense, 500), Split(checking, -500)],
        )
        manager.generate_ledger()
        total = sum(a.get_balance() for a in manager.accounts.values())
        assert total == 0, f"Trial balance is {total}, expected 0"

    def test_chronological_order(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        salary = manager.add_account("Salary", 4)
        expenses = manager.add_account("Expenses", 5)

        manager.add_transaction(
            datetime(2026, 3, 1), "March",
            [Split(expenses, 100), Split(checking, -100)],
        )
        manager.add_transaction(
            datetime(2026, 1, 1), "January",
            [Split(salary, -2000), Split(checking, 2000)],
        )
        manager.add_transaction(
            datetime(2026, 2, 1), "February",
            [Split(salary, -500), Split(checking, 500)],
        )

        ordered = manager.journal.chronological()
        dates = [txn.date.strftime("%Y-%m-%d") for txn in ordered]
        assert dates == sorted(dates)

    def test_close_temps(self, manager: AccountManager):
        """Closing temporary accounts resets income/expense to zero, updates RE."""
        checking = manager.add_account("Checking", 1)
        salary = manager.add_account("Salary", 4)
        groceries = manager.add_account("Groceries", 5)

        manager.add_transaction(
            datetime(2026, 1, 1), "Pay",
            [Split(salary, -100000), Split(checking, 100000)],
        )
        manager.add_transaction(
            datetime(2026, 1, 2), "Buy food",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        manager.generate_ledger()

        # Before close: leaf income/expense accounts have balances
        assert manager.accounts[salary].get_balance() != 0  # Salary under Income
        assert manager.accounts[groceries].get_balance() != 0  # Groceries under Expense

        manager.close_temps()
        manager.generate_ledger()

        # After close: leaf income/expense accounts reset to 0
        assert manager.accounts[salary].get_balance() == 0
        assert manager.accounts[groceries].get_balance() == 0

    def test_transaction_validate(self, manager: AccountManager):
        """JournalTransaction.validate() catches unbalanced entries."""
        good = JournalTransaction(
            datetime(2026, 1, 1), "Good",
            [Split(1, 100), Split(2, -100)],
        )
        assert good.validate() is True

        bad = JournalTransaction(
            datetime(2026, 1, 1), "Bad",
            [Split(1, 100), Split(2, -50)],
        )
        assert bad.validate() is False


class TestDataClassModels:
    """Data class behavior and serialization."""

    def test_split_default_memo(self):
        s = Split(account_id=1, amount=5000)
        assert s.memo == ""

    def test_split_custom_memo(self):
        s = Split(account_id=1, amount=5000, memo="test")
        assert s.memo == "test"

    def test_journal_total(self):
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Test",
            [Split(1, 5000), Split(2, -3000), Split(6, -2000)],
        )
        assert txn.total() == 5000  # sum of debits only

    def test_holding_dataclass(self):
        h = Holding(account_id=1, ticker="VTI", shares=100.5, cost_basis_cents=2750000)
        assert h.account_id == 1
        assert h.ticker == "VTI"
        assert h.shares == 100.5
        assert h.cost_basis_cents == 2750000

    def test_price_dataclass(self):
        p = Price(ticker="VTI", date="2026-05-13", price_cents=27500)
        assert p.ticker == "VTI"
        assert p.price_cents == 27500

    def test_journal_dict(self):
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Test",
            [Split(1, 5000), Split(2, -5000)],
        )
        d = txn.__dict__()
        assert d["description"] == "Test"
        assert len(d["splits"]) == 2

    # ── Transaction validation edge cases ─────────────────

    def test_validate_bad_returns_false(self):
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Bad",
            [Split(1, 100), Split(2, -50)],
        )
        assert txn.validate() is False

    def test_validate_single_split_fails(self):
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Single",
            [Split(1, 100)],
        )
        assert txn.validate() is False

    def test_total_empty_splits(self):
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Empty", [],
        )
        assert txn.total() == 0

    def test_total_multiple_debits(self):
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Multiple",
            [Split(1, 5000), Split(2, 3000), Split(3, -8000)],
        )
        assert txn.total() == 8000

    # ── Ledger Entry dict serialization ────────────────────

    def test_ledger_entry_dict(self):
        from ledger.models.data_class import LedgerEntry
        entry = LedgerEntry(datetime(2026, 1, 1), "Test", 0, 5000, 5000)
        d = entry.__dict__()
        assert d["debit"] == 5000
        assert d["credit"] == 0
        assert d["balance"] == 5000
        assert d["description"] == "Test"

    def test_ledger_entry_credit_dict(self):
        from ledger.models.data_class import LedgerEntry
        entry = LedgerEntry(datetime(2026, 1, 2), "Credit", 10000, 0, -10000)
        d = entry.__dict__()
        assert d["credit"] == 10000
        assert d["debit"] == 0
        assert d["balance"] == -10000
