"""Unit tests: account deletion policy — reassign children/transactions.

Tests follow TDD: define the expected behavior before implementing.

Boundary
--------
- Uses ``fast_manager`` / ``fast_seeded`` (MockDB, sub-millisecond)
- Tests reassignment logic and delete account with options
- Does NOT test the GUI dialog (see test_comp_dialogs.py)
"""

from __future__ import annotations

from datetime import datetime

import pytest

from ledger.models.data_class import Split


# ═══════════════════════════════════════════════════════════════════
#  REASSIGN CHILDREN
# ═══════════════════════════════════════════════════════════════════


class TestReassignChildren:
    """Reparenting sub-accounts when deleting a parent."""

    # ── Fixtures ────────────────────────────────────────────

    @pytest.fixture
    def setup(self, fast_manager):
        """Create a parent with two children and a target."""
        parent = fast_manager.add_account("Parent", 1)
        child1 = fast_manager.add_account("Child1", parent)
        child2 = fast_manager.add_account("Child2", parent)
        target = fast_manager.add_account("Target", 1)
        return fast_manager, parent, child1, child2, target

    # ── Happy path ──────────────────────────────────────────

    def test_reassign_children_valid(self, setup):
        """All children reparented to target."""
        mgr, parent, child1, child2, target = setup
        mgr.reassign_children(parent, target)
        assert mgr.accounts[child1].parent == target
        assert mgr.accounts[child2].parent == target

    def test_reassign_children_then_delete_parent(self, setup):
        """After moving children, the now-empty parent can be deleted."""
        mgr, parent, child1, child2, target = setup
        mgr.reassign_children(parent, target)
        mgr.delete_account(parent)
        assert parent not in mgr.accounts
        assert child1 in mgr.accounts
        assert child2 in mgr.accounts
        assert mgr.accounts[child1].parent == target

    def test_reassign_children_preserves_ledger_balance(self, setup):
        """Reparenting doesn't change account balances."""
        mgr, parent, child1, child2, target = setup

        bal_before = mgr.get_display_balance(child1)
        mgr.reassign_children(parent, target)
        bal_after = mgr.get_display_balance(child1)

        assert bal_after == bal_before

    # ── Edge cases ──────────────────────────────────────────

    def test_reassign_no_children_noop(self, fast_manager):
        """Account with no children — reassign succeeds, nothing moves."""
        acct = fast_manager.add_account("Lonely", 1)
        target = fast_manager.add_account("Target", 1)
        fast_manager.reassign_children(acct, target)
        # No error — just a no-op
        assert acct in fast_manager.accounts

    def test_reassign_to_self_error(self, setup):
        """Reassigning children to the same parent raises."""
        mgr, parent, *_ = setup
        with pytest.raises(ValueError, match="same"):
            mgr.reassign_children(parent, parent)

    def test_reassign_root_error(self, fast_manager):
        """Cannot reassign children of the root account."""
        target = fast_manager.add_account("Target", 1)
        with pytest.raises(ValueError, match="root"):
            fast_manager.reassign_children(0, target)

    def test_reassign_target_nonexistent_error(self, setup):
        """Reassigning to a non-existent account ID raises."""
        mgr, parent, *_ = setup
        with pytest.raises(ValueError, match="not found"):
            mgr.reassign_children(parent, 99999)

    def test_reassign_cycle_error(self, setup):
        """Cannot reassign a parent's children to one of its own children."""
        mgr, parent, child1, *_ = setup
        grandchild = mgr.add_account("Grandchild", child1)
        with pytest.raises(ValueError, match="cycle"):
            mgr.reassign_children(parent, grandchild)


# ═══════════════════════════════════════════════════════════════════
#  REASSIGN TRANSACTIONS
# ═══════════════════════════════════════════════════════════════════


class TestReassignTransactions:
    """Migrating transaction splits when deleting an account."""

    # ── Fixtures ────────────────────────────────────────────

    @pytest.fixture
    def funded_mgr(self, fast_seeded):
        """Seeded manager with a source account, target, and a txn on source."""
        m = fast_seeded
        source = m.add_account("Source", 1)
        target = m.add_account("Target", 1)
        equity = 6  # default equity account

        # Fund source with $1,000
        m.add_transaction(
            datetime(2026, 6, 1), "Fund source",
            [Split(source, 100000), Split(equity, -100000)],
        )
        m.generate_ledger()
        return m, source, target, equity

    # ── Happy path ──────────────────────────────────────────

    def test_reassign_transactions_valid(self, funded_mgr):
        """Splits referencing source are moved to target."""
        m, source, target, _ = funded_mgr

        source_bal = m.get_display_balance(source)
        target_bal = m.get_display_balance(target)

        m.reassign_transactions(source, target)
        m.generate_ledger()

        # Source zeroed, target got source's balance
        assert m.get_display_balance(source) == 0
        assert m.get_display_balance(target) == target_bal + source_bal

    def test_reassign_transactions_balanced_equation(self, funded_mgr):
        """After reassignment, A = L + E still holds."""
        m, source, target, _ = funded_mgr
        m.reassign_transactions(source, target)
        m.generate_ledger()
        eq = m.check_accounting_equation()
        assert eq["balanced"], "Equation unbalanced after reassign"

    def test_reassign_transactions_then_delete_source(self, funded_mgr):
        """After moving splits, source can be deleted without losing data."""
        m, source, target, _ = funded_mgr
        m.reassign_transactions(source, target)
        m.generate_ledger()

        # Now delete source
        m.delete_account(source)

        # Target should still have the balance
        assert source not in m.accounts
        assert target in m.accounts
        eq = m.check_accounting_equation()
        assert eq["balanced"]

    # ── Edge cases ──────────────────────────────────────────

    def test_reassign_no_transactions_noop(self, fast_manager):
        """Account with no transactions — reassign succeeds, nothing moves."""
        source = fast_manager.add_account("Source", 1)
        target = fast_manager.add_account("Target", 1)
        fast_manager.reassign_transactions(source, target)
        # No error — just a no-op
        assert fast_manager.get_display_balance(source) == 0

    def test_reassign_to_self_error(self, funded_mgr):
        """Reassigning splits to the same account raises."""
        m, source, *_ = funded_mgr
        with pytest.raises(ValueError, match="same"):
            m.reassign_transactions(source, source)

    def test_reassign_root_error(self, fast_manager):
        """Cannot reassign transactions from root account."""
        target = fast_manager.add_account("Target", 1)
        with pytest.raises(ValueError, match="root"):
            fast_manager.reassign_transactions(0, target)

    def test_reassign_target_nonexistent_error(self, funded_mgr):
        """Reassigning to a non-existent account raises."""
        m, source, *_ = funded_mgr
        with pytest.raises(ValueError, match="not found"):
            m.reassign_transactions(source, 99999)

    def test_partial_reassign_mixed_transactions(self, funded_mgr):
        """Only splits referencing source are moved; other splits unchanged."""
        m, source, target, equity = funded_mgr
        unrelated = m.add_account("Unrelated", 1)

        # Add a txn that involves both source and unrelated
        m.add_transaction(
            datetime(2026, 6, 2), "Mixed",
            [Split(source, -5000), Split(unrelated, 5000)],
        )
        m.generate_ledger()

        bal_before = m.get_display_balance(source)
        m.reassign_transactions(source, target)
        m.generate_ledger()

        # Source zeroed, target got source's balance
        assert m.get_display_balance(source) == 0
        assert m.get_display_balance(target) == bal_before
        # Unrelated unchanged
        assert m.get_display_balance(unrelated) == 5000


# ═══════════════════════════════════════════════════════════════════
#  DELETE ACCOUNT WITH OPTIONS
# ═══════════════════════════════════════════════════════════════════


class TestDeleteAccountWithOptions:
    """The full delete flow: reassign children/txns then delete."""

    def test_delete_simple_no_children_no_txns(self, fast_manager):
        """No complications → just delete."""
        acct = fast_manager.add_account("Simple", 1)
        fast_manager.delete_account(acct)
        assert acct not in fast_manager.accounts

    def test_delete_root_raises(self, fast_manager):
        """Root account cannot be deleted."""
        with pytest.raises(ValueError, match="root"):
            fast_manager.delete_account(0)

    def test_delete_with_children_reassigns_then_deletes(self, fast_seeded):
        """Children are reparented to target before delete."""
        m = fast_seeded
        # Use non-seeded manager to avoid conflicts
        parent = m.add_account("Parent", 1)
        child = m.add_account("Child", parent)
        target = m.add_account("NewParent", 1)

        m.reassign_children(parent, target)
        m.delete_account(parent)

        assert parent not in m.accounts
        assert m.accounts[child].parent == target

    def test_delete_with_transactions_reassigns_then_deletes(self, fast_seeded):
        """Transactions are migrated before delete."""
        m = fast_seeded
        source = m.add_account("OldSrc", 1)
        target = m.add_account("NewTarget", 1)
        equity = 6

        m.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(source, 500000), Split(equity, -500000)],
        )
        m.generate_ledger()

        m.reassign_transactions(source, target)
        m.generate_ledger()
        m.delete_account(source)

        assert source not in m.accounts
        assert target in m.accounts
        assert m.get_display_balance(target) == 500000

    def test_delete_with_both_reassigns_then_deletes(self, fast_seeded):
        """Both children and transactions handled before delete."""
        m = fast_seeded
        parent = m.add_account("Parent", 1)
        child = m.add_account("Child", parent)
        txn_target = m.add_account("TxnTarget", 1)
        child_target = m.add_account("ChildTarget", 1)
        equity = 6

        m.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(parent, 300000), Split(equity, -300000)],
        )
        m.generate_ledger()

        m.reassign_children(parent, child_target)
        m.reassign_transactions(parent, txn_target)
        m.generate_ledger()
        m.delete_account(parent)

        assert parent not in m.accounts
        assert m.accounts[child].parent == child_target
        assert m.get_display_balance(txn_target) == 300000
