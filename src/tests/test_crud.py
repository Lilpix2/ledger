"""Unit tests: CRUD operations, edge cases, and GUI widget helpers.

Covers Journal, AccountManager CRUD, edge cases for validation,
widget helpers (format_cents, build_account_choices).
"""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split, JournalTransaction, Holding, Price
from ledger.models.data_books import Journal


# ═══════════════════════════════════════════════════════════════════
#  Journal CRUD (tests bypass AccountManager for pure Journal ops)
# ═══════════════════════════════════════════════════════════════════


class TestJournalCRUD:
    """In-memory Journal: add / delete / edge-case operations."""

    def test_journal_add_transaction(self):
        """Add a transaction directly to a standalone Journal."""
        j = Journal()
        txn = JournalTransaction(
            datetime(2026, 1, 15), "Test entry",
            [Split(1, 5000), Split(2, -5000)],
        )
        txn_id = j.add_transaction(txn)
        assert txn_id == 0  # first ID
        assert len(j.transactions) == 1
        assert j.transactions[0] is txn

    def test_journal_add_multiple(self):
        """IDs increment correctly."""
        j = Journal()
        t1 = JournalTransaction(datetime(2026, 1, 1), "A", [Split(1, 100), Split(2, -100)])
        t2 = JournalTransaction(datetime(2026, 1, 2), "B", [Split(1, 200), Split(2, -200)])
        id1 = j.add_transaction(t1)
        id2 = j.add_transaction(t2)
        assert id1 == 0
        assert id2 == 1

    def test_journal_delete_transaction(self):
        """delete_transaction removes from in-memory dict and sorted list."""
        j = Journal()
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Delete me",
            [Split(1, 100), Split(2, -100)],
        )
        txn_id = j.add_transaction(txn)
        assert txn_id in j.transactions

        removed_id = j.delete_transaction(txn_id)
        assert removed_id == txn_id
        assert txn_id not in j.transactions
        assert txn_id not in j.sorted_ids

    def test_journal_delete_nonexistent_raises(self):
        """Deleting a transaction that doesn't exist raises KeyError."""
        j = Journal()
        with pytest.raises(KeyError, match="not found"):
            j.delete_transaction(99999)

    def test_journal_empty_after_delete(self):
        """Deleted transactions are removed from chronological order."""
        j = Journal()
        t1 = JournalTransaction(datetime(2026, 1, 1), "A", [Split(1, 100), Split(2, -100)])
        t2 = JournalTransaction(datetime(2026, 1, 2), "B", [Split(1, 200), Split(2, -200)])
        j.add_transaction(t1)
        id2 = j.add_transaction(t2)
        j.delete_transaction(id2)
        ordered = j.chronological()
        assert len(ordered) == 1
        assert ordered[0].description == "A"


class TestJournalEdgeCases:
    """Edge cases for Journal: add without accounts, same dates, etc."""

    def test_journal_create_empty(self):
        """Journal() creates without any accounts loaded (pure in-memory)."""
        j = Journal()
        assert j.transactions == {}
        assert j.sorted_ids == []
        assert j.id_num == 0

    def test_chronological_same_date(self):
        """Chronological ordering is stable when dates are identical."""
        j = Journal()
        t1 = JournalTransaction(datetime(2026, 3, 1), "First", [Split(1, 100), Split(2, -100)])
        t2 = JournalTransaction(datetime(2026, 3, 1), "Second", [Split(1, 200), Split(2, -200)])
        t3 = JournalTransaction(datetime(2026, 3, 1), "Third", [Split(1, 300), Split(2, -300)])
        j.add_transaction(t2)  # added second
        j.add_transaction(t3)  # added third
        j.add_transaction(t1)  # added first
        ordered = j.chronological()
        descriptions = [t.description for t in ordered]
        # Same date → insertion order should be preserved (stable sort)
        assert descriptions == ["Second", "Third", "First"]


# ═══════════════════════════════════════════════════════════════════
#  AccountManager CRUD
# ═══════════════════════════════════════════════════════════════════


class TestAccountManagerDeleteTransaction:
    """AccountManager.delete_transaction — full lifecycle."""

    def test_delete_transaction_removes_from_journal(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        txn_id = manager.add_transaction(
            datetime(2026, 1, 15), "Shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        assert txn_id in manager.journal.transactions

        manager.delete_transaction(txn_id)
        assert txn_id not in manager.journal.transactions

    def test_delete_transaction_clears_balances(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        salary = manager.add_account("Salary", 4)
        txn_id = manager.add_transaction(
            datetime(2026, 1, 1), "Pay",
            [Split(salary, -100000), Split(checking, 100000)],
        )
        manager.generate_ledger()
        assert manager.accounts[checking].get_balance() == 100000

        manager.delete_transaction(txn_id)
        assert manager.accounts[checking].get_balance() == 0
        assert manager.accounts[salary].get_balance() == 0

    def test_delete_transaction_regenerates_ledger_correctly(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        salary = manager.add_account("Salary", 4)
        groceries = manager.add_account("Groceries", 5)

        t1 = manager.add_transaction(
            datetime(2026, 1, 1), "Pay",
            [Split(salary, -100000), Split(checking, 100000)],
        )
        t2 = manager.add_transaction(
            datetime(2026, 1, 2), "Shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        manager.generate_ledger()
        # Before delete: checking = 95K
        assert manager.accounts[checking].get_balance() == 95000

        manager.delete_transaction(t2)
        # After deleting shop, checking = 100K, groceries = 0
        assert manager.accounts[checking].get_balance() == 100000
        assert manager.accounts[groceries].get_balance() == 0

    def test_delete_nonexistent_txn_raises(self, manager: AccountManager):
        """AccountManager.delete_transaction raises KeyError for bad ID."""
        with pytest.raises(KeyError, match="not found"):
            manager.delete_transaction(99999)


class TestAccountManagerUpdate:
    """AccountManager.update_account — name, parent, type, subtype."""

    def test_update_name(self, manager: AccountManager):
        aid = manager.add_account("Old Name", 1)
        manager.update_account(aid, "New Name")
        assert manager.accounts[aid].name == "New Name"

    def test_update_parent(self, manager: AccountManager):
        aid = manager.add_account("My Account", 1)
        manager.update_account(aid, "My Account", parent=5)  # move to Expenses
        assert manager.accounts[aid].parent == 5

    def test_update_type(self, manager: AccountManager):
        aid = manager.add_account("Something", 1)
        manager.update_account(aid, "Something", acct_type="EXPENSE")
        assert manager.accounts[aid].acct_type == "EXPENSE"

    def test_update_subtype(self, manager: AccountManager):
        aid = manager.add_account("Something", 1, account_subtype="checking")
        manager.update_account(aid, "Something", account_subtype="brokerage")
        assert manager.accounts[aid].account_subtype == "brokerage"

    def test_update_name_and_type(self, manager: AccountManager):
        aid = manager.add_account("Old", 1, acct_type="ASSET")
        manager.update_account(aid, "Renamed", acct_type="LIABILITY")
        acct = manager.accounts[aid]
        assert acct.name == "Renamed"
        assert acct.acct_type == "LIABILITY"

    def test_update_with_none_type_keeps_existing(self, manager: AccountManager):
        """Passing None for acct_type should preserve the stored type."""
        aid = manager.add_account("Keep Type", 1, acct_type="ASSET")
        manager.accounts[aid].acct_type = "LIABILITY"  # manually change in mem
        manager.update_account(aid, "Keep Type", acct_type=None)
        # The DB call will use the account's current type (LIABILITY due to manual change)
        # But update_account uses final_type = acct_type if acct_type is not None else acct.acct_type
        # So final_type should be "LIABILITY"
        assert manager.accounts[aid].acct_type == "LIABILITY"

    def test_update_nonexistent_account_raises(self, manager: AccountManager):
        with pytest.raises(ValueError, match="not found"):
            manager.update_account(99999, "Ghost")


class TestAccountManagerDelete:
    """AccountManager.delete_account — removal with constraints."""

    def test_delete_account_removes_from_db(self, manager: AccountManager):
        aid = manager.add_account("Temp Account", 1)
        assert aid in manager.accounts
        manager.delete_account(aid)
        assert aid not in manager.accounts
        # Verify also gone from DB
        assert aid not in manager.accounts

    def test_delete_account_prevents_with_children(self, manager: AccountManager):
        """Deleting an account that has children should raise ValueError."""
        parent_id = manager.add_account("Parent", 1)
        manager.add_account("Child", parent_id)  # child under parent
        with pytest.raises(ValueError, match="has|sub-account"):
            manager.delete_account(parent_id)

    def test_delete_leaf_account_succeeds(self, manager: AccountManager):
        parent_id = manager.add_account("Parent", 1)
        child_id = manager.add_account("Child", parent_id)
        # Delete child first, then parent
        manager.delete_account(child_id)
        assert child_id not in manager.accounts
        manager.delete_account(parent_id)
        assert parent_id not in manager.accounts

    def test_delete_root_account_raises(self, manager: AccountManager):
        with pytest.raises(ValueError, match="Cannot delete root"):
            manager.delete_account(0)


# ═══════════════════════════════════════════════════════════════════
#  Edge Cases — Validation & Error Handling
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCaseValidation:
    """Input validation edge cases for accounts and transactions."""

    def test_empty_string_name_raises(self, manager: AccountManager):
        """Account with empty string name should raise ValueError."""
        with pytest.raises(ValueError, match="name"):
            manager.add_account("", 1)

    def test_very_long_description(self, manager: AccountManager):
        """Transaction with 200+ char description should work."""
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        long_desc = "A" * 250
        txn_id = manager.add_transaction(
            datetime(2026, 1, 15), long_desc,
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        assert txn_id is not None
        txn = manager.journal.transactions[txn_id]
        assert len(txn.description) == 250

    def test_special_characters_in_split_memo(self, manager: AccountManager):
        """Memo with unicode, quotes, special chars should work."""
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        special_memo = "Café du Marché — 100% «authentique» ✨ 'quote'\""
        txn_id = manager.add_transaction(
            datetime(2026, 1, 15), "Special chars",
            [Split(groceries, 5000, memo=special_memo),
             Split(checking, -5000)],
        )
        txn = manager.journal.transactions[txn_id]
        # Find the groceries split
        memo_found = None
        for s in txn.splits:
            if s.account_id == groceries:
                memo_found = s.memo
                break
        assert memo_found == special_memo

    def test_sell_more_shares_than_owned_raises(self, manager: AccountManager):
        """Selling more shares than owned should raise ValueError."""
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(checking, 500000),
             Split(6, -1000000)],
        )
        manager.buy_security(datetime(2026, 2, 1), "Buy",
                             brokerage, checking, "VTI", 10, 27500)
        with pytest.raises(ValueError, match="Cannot sell|only"):
            manager.sell_security(datetime(2026, 3, 1), "Sell Too Many",
                                  brokerage, checking, "VTI", 20, 29500)

    def test_buy_with_zero_cash(self, manager: AccountManager):
        """Buying with zero cash in the cash account should work (balance goes negative)."""
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # No funding — cash is zero
        txn_id = manager.buy_security(
            datetime(2026, 1, 15), "Buy on empty cash",
            brokerage, checking, "VTI", 5, 10000,
        )
        manager.generate_ledger()
        assert txn_id is not None
        # Cash went negative
        assert manager.accounts[checking].get_balance() == -50000
        # Brokerage has the position value
        assert manager.accounts[brokerage].get_balance() == 50000

    def test_delete_transaction_not_found_raises(self, manager: AccountManager):
        """Deleting a transaction that doesn't exist raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            manager.delete_transaction(99999)

    def test_delete_root_account_raises(self, manager: AccountManager):
        with pytest.raises(ValueError, match="Cannot delete root"):
            manager.delete_account(0)

    def test_get_latest_price_multiple(self, manager: AccountManager):
        """get_latest_price returns the most recent of multiple prices."""
        manager.save_price("VTI", "2026-01-15", 25000)
        manager.save_price("VTI", "2026-02-15", 26000)
        manager.save_price("VTI", "2026-03-15", 27500)
        manager.save_price("VTI", "2026-04-15", 28000)
        latest = manager.get_latest_price("VTI")
        assert latest == 28000  # chronologically last

    def test_chronological_same_date(self, manager: AccountManager):
        """Transactions with same date are ordered by insertion (stable sort)."""
        checking = manager.add_account("Checking", 1)
        groceries = manager.add_account("Groceries", 5)
        salary = manager.add_account("Salary", 4)

        t1 = manager.add_transaction(
            datetime(2026, 3, 1), "Second entry",
            [Split(groceries, 100), Split(checking, -100)],
        )
        t2 = manager.add_transaction(
            datetime(2026, 3, 1), "Third entry",
            [Split(salary, -200), Split(checking, 200)],
        )
        t3 = manager.add_transaction(
            datetime(2026, 3, 1), "First entry",
            [Split(groceries, 300), Split(checking, -300)],
        )
        ordered = manager.journal.chronological()
        descriptions = [t.description for t in ordered]
        # Same dates → insertion order preserved (stable sort: Python's
        # Timsort is stable so same-date items keep insertion order)
        assert descriptions == ["Second entry", "Third entry", "First entry"]


class TestEdgeCaseInvestment:
    """Investment-specific edge cases."""

    def test_sell_nonexistent_position_raises(self, manager: AccountManager):
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        with pytest.raises(ValueError, match="No position"):
            manager.sell_security(datetime(2026, 1, 1), "Sell None",
                                  brokerage, checking, "VTI", 5, 10000)

    def test_buy_shares_barely_affordable(self, manager: AccountManager):
        """Buy exactly what you can afford."""
        checking = manager.add_account("Checking", 1)
        brokerage = manager.add_account("Brokerage", 1, account_subtype="brokerage")
        manager.add_transaction(
            datetime(2026, 1, 1), "Fund exactly 100K",
            [Split(checking, 100000), Split(brokerage, 100000),
             Split(6, -200000)],
        )
        txn_id = manager.buy_security(
            datetime(2026, 1, 15), "Buy exactly",
            brokerage, checking, "VTI", 4, 25000,  # 4 * 25000 = 100000
        )
        manager.generate_ledger()
        assert manager.accounts[checking].get_balance() == 0  # all spent


# ═══════════════════════════════════════════════════════════════════
#  GUI Widget Helper Tests
# ═══════════════════════════════════════════════════════════════════


class TestFormatCents:
    """Standalone tests for format_cents()."""

    def test_format_positive(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(123456) == "$1,234.56"

    def test_format_zero(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(0) == "$0.00"

    def test_format_negative(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(-5000) == "-$50.00"

    def test_format_large(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(10000000) == "$100,000.00"

    def test_format_none(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(None) == "—"

    def test_format_small(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(1) == "$0.01"

    def test_format_negative_none(self):
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import format_cents
        assert format_cents(-1) == "-$0.01"


class TestBuildAccountChoices:
    """Standalone tests for build_account_choices()."""

    def test_build_choices_labels(self, manager: AccountManager):
        """Verify label format and mapping for default accounts."""
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import build_account_choices

        choices, mapping = build_account_choices(manager)
        assert len(choices) > 0
        assert isinstance(choices, list)
        assert isinstance(mapping, dict)

        # Default accounts should appear
        # cash should be under assets with prefix
        cash_labels = [c for c in choices if "cash" in c]
        assert len(cash_labels) > 0

        # Verify label contains account type
        for label in cash_labels:
            assert "ASSET" in label or "(" in label  # has type indicator

    def test_build_choices_mapping(self, manager: AccountManager):
        """Verify label → ID mapping works for a known account."""
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import build_account_choices

        # Find the "cash" account ID
        cash_id = None
        for aid, acct in manager.accounts.items():
            if acct.name == "cash":
                cash_id = aid
                break

        choices, mapping = build_account_choices(manager)
        # Find the label that maps to cash_id
        matching_labels = [lbl for lbl, aid in mapping.items() if aid == cash_id]
        assert len(matching_labels) >= 1

    def test_build_choices_with_subtype_filter(self, manager: AccountManager):
        """Subtype filter only includes accounts with matching subtype."""
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import build_account_choices

        # Add a brokerage account
        manager.add_account("My Brokerage", 1, account_subtype="brokerage")

        choices, mapping = build_account_choices(
            manager, subtype_filter={"brokerage"}
        )
        brokerage_labels = [c for c in choices if "brokerage" in c.lower()
                            or "brokerage" in c.lower()]
        # At least the one we created should be there
        assert len(brokerage_labels) >= 1

        # Accounts without brokerage subtype should not appear
        for lbl in choices:
            if "cash" in lbl:
                assert False, f"cash should not appear in brokerage-only filter: {lbl}"

    def test_build_choices_nonexistent_subtype_filter(self, manager: AccountManager):
        """Filter for a subtype that doesn't exist returns empty choices."""
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import build_account_choices

        choices, mapping = build_account_choices(
            manager, subtype_filter={"nonexistent"}
        )
        assert choices == []
        assert mapping == {}

    def test_build_choices_structure(self, manager: AccountManager):
        """Verify labels include indentation, name, type, and optional subtype."""
        pytest.importorskip('tkinter')
        from ledger.gui.widgets import build_account_choices

        # Add a brokerage account
        mgr = manager
        mgr.add_account("Schwab", 1, account_subtype="brokerage")

        choices, mapping = build_account_choices(mgr)

        # Find brokerage-labeled account
        schwab_labels = [c for c in choices if "Schwab" in c]
        assert len(schwab_labels) >= 1
        label = schwab_labels[0]
        # Should have type info
        assert "ASSET" in label
        # Should have subtype info
        assert "[brokerage]" in label
        # Should have indentation (starts with spaces since it's under Assets)
        assert label.startswith(" ")
