"""Component tests: ``gui/dialogs.py`` — DeleteAccountDialog.

Tests the delete account dialog's orchestration:
  • Shows child reassignment section when children exist
  • Shows transaction reassignment section when txns exist
  • Reassigns children and/or transactions before deletion
  • Simple confirm when no complications
  • Cancel does nothing
  • Root account blocked

Boundary
--------
- Backend mocked via ``fast_manager`` (MockDB)
- ``messagebox.showerror / askyesno`` patched globally
- ``wait_window`` patched so ``__init__`` returns immediately
- ``on_success`` is a ``MagicMock``

Black-box
---------
Interaction through button ``.invoke()``, combobox ``.set()``,
entry ``delete/insert``. No private state inspection.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    pytest.skip("tkinter not available", allow_module_level=True)
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from ledger.models.data_class import Split
from ledger.constants import DATE_STR

from .conftest import (
    first_widget,
    all_widgets,
    first_entry,
    set_entry_text,
    button_invoke,
    walk,
)


_DIALOGS_MOD = "ledger.gui.dialogs"


@pytest.fixture(autouse=True)
def _auto_patch_dialogs():
    """Patches ``wait_window`` and ``messagebox.showerror/askyesno``."""
    with patch.object(tk.Misc, "wait_window"):
        with patch(f"{_DIALOGS_MOD}.messagebox.showerror") as mock_error:
            with patch(f"{_DIALOGS_MOD}.messagebox.askyesno", return_value=True):
                yield mock_error


@pytest.fixture
def mock_success():
    return MagicMock()


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════


def _find_label_frame(parent: tk.Widget, text: str) -> ttk.LabelFrame:
    for w in walk(parent):
        if isinstance(w, ttk.LabelFrame):
            try:
                if str(w.cget("text")) == text:
                    return w
            except tk.TclError:
                pass
    raise AssertionError(f"LabelFrame '{text}' not found")


# ═══════════════════════════════════════════════════════════════════
#  DeleteAccountDialog
# ═══════════════════════════════════════════════════════════════════


class TestDeleteAccountDialog:
    """Delete account dialog with child/txn reassignment options."""

    # ── No complications — simple delete ────────────────────

    def test_simple_delete_no_children_no_txns(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Account with no children and no transactions — simple confirm."""
        mock_error = _auto_patch_dialogs
        acct_id = fast_seeded.add_account("Simple", 1)

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, acct_id, mock_success)

        # Should show a simple confirmation
        # The confirm button calls delete_account → refresh
        # Verify on_success fired
        mock_success.assert_called_once()
        assert acct_id not in fast_seeded.accounts

    def test_simple_delete_no_children_no_txns_no_extra_sections(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """No children/txn sections shown when not needed."""
        acct_id = fast_seeded.add_account("Simple", 1)

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, acct_id, mock_success)

        # LabelFrames for children and txns should NOT exist
        # (they'd only appear if > 0)
        with pytest.raises(AssertionError):
            _find_label_frame(dlg.dialog, "Sub-accounts")
        with pytest.raises(AssertionError):
            _find_label_frame(dlg.dialog, "Transactions")

    # ── Root account blocked ──────────────────────────────

    def test_delete_root_shows_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Root account deletion shows showerror."""
        mock_error = _auto_patch_dialogs

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, 0, mock_success)

        mock_error.assert_called_once()
        mock_success.assert_not_called()

    # ── With children ──────────────────────────────────────

    def test_children_section_shown(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """When account has children, the sub-accounts section appears."""
        parent = fast_seeded.add_account("Parent", 1)
        fast_seeded.add_account("Child", parent)

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, parent, mock_success)

        frame = _find_label_frame(dlg.dialog, "Sub-accounts")
        assert frame is not None

    def test_children_reassigned_via_dropdown(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Selecting a target for children → children reparented."""
        parent = fast_seeded.add_account("Parent", 1)
        child = fast_seeded.add_account("Child", parent)
        target = fast_seeded.add_account("TargetParent", 1)

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, parent, mock_success)

        # Find the child-reassign combobox in the Sub-accounts frame
        child_frame = _find_label_frame(dlg.dialog, "Sub-accounts")
        combo = first_widget(child_frame, ttk.Combobox)
        assert combo is not None, "No child reassign combo found"

        # Select the target
        choices = list(combo.cget("values"))
        target_label = next(c for c in choices if "TargetParent" in c)
        combo.set(target_label)

        # Click the delete button
        button_invoke(dlg.dialog, "Delete Account")

        mock_success.assert_called_once()
        assert parent not in fast_seeded.accounts
        assert fast_seeded.accounts[child].parent == target

    # ── With transactions ──────────────────────────────────

    def test_transactions_section_shown(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """When account has transactions, the transactions section appears."""
        source = fast_seeded.add_account("Source", 1)
        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(source, 100000), Split(6, -100000)],
        )
        fast_seeded.generate_ledger()

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, source, mock_success)

        frame = _find_label_frame(dlg.dialog, "Transactions")
        assert frame is not None

    def test_transactions_reassigned_via_dropdown(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Selecting a target for transactions → splits migrated."""
        source = fast_seeded.add_account("Source", 1)
        target = fast_seeded.add_account("Target", 1)
        equity = 6

        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(source, 200000), Split(equity, -200000)],
        )
        fast_seeded.generate_ledger()

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, source, mock_success)

        txn_frame = _find_label_frame(dlg.dialog, "Transactions")
        combo = first_widget(txn_frame, ttk.Combobox)
        assert combo is not None, "No txn reassign combo found"

        choices = list(combo.cget("values"))
        target_label = next(c for c in choices if "Target" in c)
        combo.set(target_label)

        button_invoke(dlg.dialog, "Delete Account")

        mock_success.assert_called_once()
        assert source not in fast_seeded.accounts
        assert fast_seeded.get_display_balance(target) == 200000

    # ── Both children and transactions ─────────────────────

    def test_both_sections_shown(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Both sections visible when account has children and txns."""
        parent = fast_seeded.add_account("Parent", 1)
        fast_seeded.add_account("Child", parent)
        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(parent, 50000), Split(6, -50000)],
        )
        fast_seeded.generate_ledger()

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, parent, mock_success)

        child_frame = _find_label_frame(dlg.dialog, "Sub-accounts")
        txn_frame = _find_label_frame(dlg.dialog, "Transactions")
        assert child_frame is not None
        assert txn_frame is not None

    def test_both_reassigned(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Both children and transactions reassigned before delete."""
        parent = fast_seeded.add_account("Parent", 1)
        child = fast_seeded.add_account("Child", parent)
        txn_target = fast_seeded.add_account("TxnTarget", 1)
        child_target = fast_seeded.add_account("ChildTarget", 1)
        equity = 6

        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(parent, 150000), Split(equity, -150000)],
        )
        fast_seeded.generate_ledger()

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, parent, mock_success)

        # Set child reassign
        child_frame = _find_label_frame(dlg.dialog, "Sub-accounts")
        child_combo = first_widget(child_frame, ttk.Combobox)
        child_choices = list(child_combo.cget("values"))
        child_label = next(c for c in child_choices if "ChildTarget" in c)
        child_combo.set(child_label)

        # Set txn reassign
        txn_frame = _find_label_frame(dlg.dialog, "Transactions")
        txn_combo = first_widget(txn_frame, ttk.Combobox)
        txn_choices = list(txn_combo.cget("values"))
        txn_label = next(c for c in txn_choices if "TxnTarget" in c)
        txn_combo.set(txn_label)

        button_invoke(dlg.dialog, "Delete Account")

        mock_success.assert_called_once()
        assert parent not in fast_seeded.accounts
        assert fast_seeded.accounts[child].parent == child_target
        assert fast_seeded.get_display_balance(txn_target) == 150000

    # ── Cancel ─────────────────────────────────────────────

    def test_cancel_does_nothing(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Cancel button aborts without changes."""
        acct = fast_seeded.add_account("CancelTest", 1)
        before = len(fast_seeded.accounts)

        # Mock askyesno to return False (user says no)
        with patch(f"{_DIALOGS_MOD}.messagebox.askyesno", return_value=False):
            # For the simple path, this triggers cancel
            pass

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, acct, mock_success)

        # Find cancel button and invoke
        button_invoke(dlg.dialog, "Cancel")

        mock_success.assert_not_called()
        assert len(fast_seeded.accounts) == before

    # ── Error path ─────────────────────────────────────────

    def test_delete_nonexistent_account_shows_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Trying to delete an account that doesn't exist shows error."""
        mock_error = _auto_patch_dialogs

        from ledger.gui.dialogs import DeleteAccountDialog
        dlg = DeleteAccountDialog(tk_root, fast_seeded, 99999, mock_success)

        mock_error.assert_called_once()
        mock_success.assert_not_called()
