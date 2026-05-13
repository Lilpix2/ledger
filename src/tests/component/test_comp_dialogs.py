"""Component tests: ``gui/dialogs.py`` — modal dialog widgets.

Tests
-----
- ``AccountDialog`` — create vs edit mode, validation, submission flow
- ``TransactionDialog`` — split management (add/remove/edit), validation
- ``BuySellDialog`` — direction toggle, field validation, submission

Boundary
--------
- Backend mocked via ``fast_manager`` / ``fast_seeded`` (MockDB)
- ``messagebox.showerror`` patched globally to suppress modal popups
- ``wait_window`` patched so dialog ``__init__`` returns immediately
- ``on_success`` is a ``MagicMock``

Black-box
---------
All interaction is through the widget surface: button ``.invoke()``,
entry ``delete/insert``, combobox ``.set()``. No private state inspected.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    pytest.skip("tkinter not available (install python3-tk)", allow_module_level=True)
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from ledger.gui.dialogs import AccountDialog, TransactionDialog, BuySellDialog
from ledger.models.data_class import Split, JournalTransaction
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


# ── Auto-patch all dialog tests ─────────────────────────────────────
# ``wait_window`` is silenced so ``__init__`` returns immediately.
# ``showerror`` is captured so we can assert errors without modal popups.


@pytest.fixture(autouse=True)
def _auto_patch_dialogs():
    """Patches ``wait_window`` and ``messagebox.showerror`` for every test.

    Tests that need to assert on error messages should declare this
    fixture in their parameter list:
        def test_something(self, _auto_patch_dialogs, ...):
            _auto_patch_dialogs.assert_called_once()
    """
    with patch.object(tk.Misc, "wait_window"):
        with patch(f"{_DIALOGS_MOD}.messagebox.showerror") as mock:
            yield mock


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════


def _find_treeview(parent):
    return first_widget(parent, ttk.Treeview)


def _tree_row_count(tree):
    return len(tree.get_children())


def _find_label_frame(parent: tk.Widget, text: str) -> ttk.LabelFrame:
    """Find a LabelFrame by its text property."""
    for w in walk(parent):
        if isinstance(w, ttk.LabelFrame):
            try:
                if str(w.cget("text")) == text:
                    return w
            except tk.TclError:
                pass
    raise AssertionError(f"LabelFrame '{text}' not found")


def _find_first_plain_entry(parent: tk.Widget) -> ttk.Entry:
    """First ``ttk.Entry`` that is NOT a ``ttk.Combobox``."""
    for w in walk(parent):
        if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox):
            return w
    raise AssertionError("No plain Entry widget found")


def _select_last_combo_value(combo: ttk.Combobox) -> str:
    """Set a combobox to its last value and return it."""
    choices = list(combo.cget("values"))
    assert choices, "Combobox has no choices"
    combo.set(choices[-1])
    return choices[-1]


# ═══════════════════════════════════════════════════════════════════
#  AccountDialog
# ═══════════════════════════════════════════════════════════════════

# The helper above is wrong. Fix.
del _find_first_plain_entry


class TestAccountDialog:
    """Create/edit account modal."""

    # ── Create mode ────────────────────────────────────────

    def test_opens_with_create_title(self, tk_root, fast_seeded, mock_success):
        """Default mode: 'New Account' title."""
        dlg = AccountDialog(tk_root, fast_seeded, mock_success)
        assert dlg.dialog.winfo_exists()
        assert dlg.dialog.title() == "New Account"

    def test_empty_name_shows_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Submit with no name → showerror called, on_success not called."""
        dlg = AccountDialog(tk_root, fast_seeded, mock_success)
        button_invoke(dlg.dialog, "Create")
        _auto_patch_dialogs.assert_called_once()
        mock_success.assert_not_called()

    def test_valid_submit_creates_account(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Valid submission → on_success called and account created."""
        dlg = AccountDialog(tk_root, fast_seeded, mock_success)

        # Fill name
        entry = first_entry(dlg.dialog)
        assert entry is not None
        set_entry_text(entry, "Test Account")

        button_invoke(dlg.dialog, "Create")

        _auto_patch_dialogs.assert_not_called()
        mock_success.assert_called_once()

        # Verify the account was actually created in the backend
        assert any(
            a.name == "Test Account" for a in fast_seeded.accounts.values()
        ), "Account not created on backend"

    def test_empty_parent_shows_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Cleared parent combo → showerror."""
        dlg = AccountDialog(tk_root, fast_seeded, mock_success)

        # Clear the parent combo
        combo = first_widget(dlg.dialog, ttk.Combobox)
        if combo:
            combo.set("")

        entry = first_entry(dlg.dialog)
        set_entry_text(entry, "Orphan Account")
        button_invoke(dlg.dialog, "Create")

        _auto_patch_dialogs.assert_called_once()
        mock_success.assert_not_called()

    # ── Edit mode ──────────────────────────────────────────

    def test_edit_opens_with_edit_title(self, tk_root, fast_seeded, mock_success):
        """Edit mode: 'Edit Account' title."""
        aid = fast_seeded.add_account("Old Name", 1)
        dlg = AccountDialog(
            tk_root, fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )
        assert dlg.dialog.title() == "Edit Account"

    def test_edit_prepopulates_name(
        self, tk_root, fast_seeded, mock_success
    ):
        """Edit mode pre-fills the account name field."""
        aid = fast_seeded.add_account("Editable Acct", 1)
        dlg = AccountDialog(
            tk_root, fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )
        entry = first_entry(dlg.dialog)
        assert entry is not None
        assert "Editable Acct" in entry.get()

    def test_edit_submit_updates_account(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Submitting in edit mode calls update_account."""
        aid = fast_seeded.add_account("Before Edit", 1)
        dlg = AccountDialog(
            tk_root, fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )

        entry = first_entry(dlg.dialog)
        set_entry_text(entry, "After Edit")
        button_invoke(dlg.dialog, "Save")

        _auto_patch_dialogs.assert_not_called()
        mock_success.assert_called_once()

        assert fast_seeded.accounts[aid].name == "After Edit", (
            f"Account not renamed: {fast_seeded.accounts[aid].name}"
        )


# ═══════════════════════════════════════════════════════════════════
#  TransactionDialog
# ═══════════════════════════════════════════════════════════════════


class TestTransactionDialog:
    """Multi-split journal entry dialog."""

    def test_opens(self, tk_root, fast_seeded, mock_success):
        """Dialog opens with 'New Transaction' title."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        assert dlg.dialog.winfo_exists()
        assert dlg.dialog.title() == "New Transaction"

    def test_add_split_inserts_row(self, tk_root, fast_seeded, mock_success):
        """Adding a valid split creates a row in the Treeview."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        add_frame = _find_label_frame(dlg.dialog, "Add Split")

        tree = _find_treeview(dlg.dialog)
        before = _tree_row_count(tree)

        _fill_add_split(add_frame)
        button_invoke(add_frame, "Add Split")

        assert _tree_row_count(tree) == before + 1

    def test_add_split_zero_amount_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Adding a split with 0 amount → showerror."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        add_frame = _find_label_frame(dlg.dialog, "Add Split")

        _fill_add_split(add_frame, amount_cents="0")
        button_invoke(add_frame, "Add Split")

        _auto_patch_dialogs.assert_called_once()

    def test_submit_unbalanced_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Submitting an unbalanced split list → showerror."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        add_frame = _find_label_frame(dlg.dialog, "Add Split")

        _fill_add_split(add_frame)
        button_invoke(add_frame, "Add Split")

        _auto_patch_dialogs.reset_mock()
        _fill_meta(dlg)
        button_invoke(dlg.dialog, "Submit")

        _auto_patch_dialogs.assert_called_once()
        mock_success.assert_not_called()

    def test_submit_balanced_succeeds(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Two balanced splits → on_success called."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        add_frame = _find_label_frame(dlg.dialog, "Add Split")

        # Split 1: debit 1000
        _fill_add_split(add_frame, amount_cents="1000")
        button_invoke(add_frame, "Add Split")

        # Split 2: credit 1000  (toggle the debit checkbox)
        _fill_add_split(add_frame, amount_cents="1000")
        debit_cb = first_widget(add_frame, ttk.Checkbutton, "Debit")
        if debit_cb:
            debit_cb.invoke()  # toggle Debit→Credit
        button_invoke(add_frame, "Add Split")

        _fill_meta(dlg)
        _auto_patch_dialogs.reset_mock()
        button_invoke(dlg.dialog, "Submit")

        assert _auto_patch_dialogs.call_count == 0, (
            f"Unexpected showerror: {_auto_patch_dialogs.call_args}"
        )
        mock_success.assert_called_once()

    def test_remove_split_deletes_row(self, tk_root, fast_seeded, mock_success):
        """Remove button deletes selected row."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        add_frame = _find_label_frame(dlg.dialog, "Add Split")

        _fill_add_split(add_frame)
        button_invoke(add_frame, "Add Split")

        tree = _find_treeview(dlg.dialog)
        assert _tree_row_count(tree) == 1

        # Select and remove
        children = tree.get_children()
        tree.selection_set(children[0])
        button_invoke(add_frame, "Remove")

        assert _tree_row_count(tree) == 0

    def test_edit_split_fills_form_and_removes_old(
        self, tk_root, fast_seeded, mock_success,
    ):
        """Edit button re-populates the form and removes the old row."""
        dlg = TransactionDialog(tk_root, fast_seeded, mock_success)
        add_frame = _find_label_frame(dlg.dialog, "Add Split")

        _fill_add_split(add_frame)
        button_invoke(add_frame, "Add Split")

        tree = _find_treeview(dlg.dialog)
        tree.selection_set(tree.get_children()[0])
        button_invoke(add_frame, "Edit")

        # Old row removed
        assert _tree_row_count(tree) == 0


# ═══════════════════════════════════════════════════════════════════
#  BuySellDialog
# ═══════════════════════════════════════════════════════════════════


class TestBuySellDialog:
    """Buy/sell security modal."""

    def test_opens(self, tk_root, fast_seeded, mock_success):
        """Dialog opens with correct title."""
        dlg = BuySellDialog(tk_root, fast_seeded, mock_success)
        assert dlg.dialog.winfo_exists()
        assert dlg.dialog.title() == "Buy / Sell Security"

    def test_gains_field_shows_on_sell(self, tk_root, fast_seeded, mock_success):
        """Toggling to Sell makes the gains account field visible."""
        dlg = BuySellDialog(tk_root, fast_seeded, mock_success)

        sell_btn = first_widget(dlg.dialog, ttk.Radiobutton, "Sell")
        assert sell_btn is not None
        sell_btn.invoke()

        # Verify gains label appears
        gains_label = first_widget(dlg.dialog, ttk.Label, "Gains Account (optional):")
        assert gains_label is not None, "Gains label missing after Sell toggle"

    def test_missing_investment_shows_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Submit with empty investment acct → showerror."""
        dlg = BuySellDialog(tk_root, fast_seeded, mock_success)
        button_invoke(dlg.dialog, "Submit")
        _auto_patch_dialogs.assert_called_once()
        mock_success.assert_not_called()

    def test_missing_ticker_shows_error(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Submit without ticker → showerror."""
        dlg = BuySellDialog(tk_root, fast_seeded, mock_success)

        all_combos = all_widgets(dlg.dialog, ttk.Combobox)
        for combo in all_combos[:2]:  # investment + cash
            choices = list(combo.cget("values"))
            if choices:
                combo.set(choices[-1])

        _auto_patch_dialogs.reset_mock()
        button_invoke(dlg.dialog, "Submit")
        _auto_patch_dialogs.assert_called_once()
        mock_success.assert_not_called()

    def test_valid_buy_submit(
        self, tk_root, fast_seeded, mock_success, _auto_patch_dialogs,
    ):
        """Completely filled Buy form → on_success called."""
        dlg = BuySellDialog(tk_root, fast_seeded, mock_success)

        all_combos = all_widgets(dlg.dialog, ttk.Combobox)
        for combo in all_combos[:2]:
            choices = list(combo.cget("values"))
            if choices:
                combo.set(choices[-1])

        entries = [w for w in walk(dlg.dialog)
                   if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
        if len(entries) >= 3:
            set_entry_text(entries[0], "VTI")    # ticker
            set_entry_text(entries[1], "10")      # shares
            set_entry_text(entries[2], "27500")   # price

        _auto_patch_dialogs.reset_mock()
        button_invoke(dlg.dialog, "Submit")

        assert _auto_patch_dialogs.call_count == 0, (
            f"Unexpected showerror: {_auto_patch_dialogs.call_args}"
        )
        mock_success.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
#  ADD SPLIT HELPERS
# ═══════════════════════════════════════════════════════════════════


def _fill_add_split(
    add_frame: ttk.LabelFrame,
    amount_cents: str = "1000",
):
    """Fill in the Add Split form with the last account choice and amount."""
    combo = first_widget(add_frame, ttk.Combobox)
    assert combo is not None, "No combo in Add Split frame"
    _select_last_combo_value(combo)

    amt_entry = _first_plain_entry(add_frame)
    set_entry_text(amt_entry, amount_cents)


def _first_plain_entry(parent) -> ttk.Entry:
    """First ttk.Entry that isn't a ttk.Combobox."""
    for w in walk(parent):
        if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox):
            return w
    raise AssertionError("No plain Entry found")


def _fill_meta(dlg):
    """Fill the date and description fields in a TransactionDialog."""
    all_combos = all_widgets(dlg.dialog, ttk.Combobox)  # first combo is in add-split frame
    # Date is row 0, col 1; Desc is row 1, col 1

    dlg_win = dlg.dialog
    entries = [w for w in walk(dlg_win)
               if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
    if entries:
        set_entry_text(entries[0], datetime.now().strftime(DATE_STR))
    if len(entries) > 1:
        set_entry_text(entries[1], "Component test txn")
