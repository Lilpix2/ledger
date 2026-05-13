"""Tests for CRUD operations through GUI dialogs and keyboard bindings.

These tests verify that:
- Dialogs can be constructed and closed without crashing
- Account/Transaction/BuySell dialogs wire up correctly
- Keyboard bindings are registered on the app and transaction table
- Account creation, deletion, transaction creation all pass through
  the dialog callbacks

Note: GUI tests require a display (X11/Wayland/Xvfb).
Skipped automatically when no display is available.
"""

import os
import tempfile
from datetime import datetime

import pytest

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


# ── Display check ──────────────────────────────────────────────────


def _has_tkinter_display() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


HAS_DISPLAY = _has_tkinter_display()
no_display = pytest.mark.skipif(not HAS_DISPLAY, reason="No display available")

@pytest.fixture(autouse=True)
def _close_tkinter_windows():
    """Destroy any leftover tkinter windows after each test."""
    yield
    if HAS_DISPLAY:
        try:
            import tkinter as tk
            root = tk._default_root
            if root is not None:
                for child in list(root.children.values()):
                    try:
                        child.destroy()
                    except Exception:
                        pass
        except Exception:
            pass


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def seeded_db() -> str:
    """Path to a seeded SQLite database with realistic data."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)

    ids = {acct.name: aid for aid, acct in mgr.accounts.items() if aid}

    mgr.add_transaction(
        datetime(2026, 1, 1), "Opening balances",
        [
            Split(ids["HS Checking"], 5000000),
            Split(ids["Schwab Brokerage"], 2000000),
            Split(ids["Discover"], -530000),
            Split(6, -6470000),
        ],
    )
    mgr.add_transaction(
        datetime(2026, 6, 1), "Payday",
        [Split(ids["Wages"], -300000), Split(ids["HS Checking"], 300000)],
    )

    mgr.generate_ledger()
    del mgr
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ── String formatting helper ───────────────────────────────────────


def _format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


# ═══════════════════════════════════════════════════════════════════
#  DIALOG CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════


@no_display
class TestDialogConstruction:
    """Dialogs can be constructed and close cleanly."""

    def test_account_dialog_constructed(self, seeded_db: str):
        """AccountDialog can be constructed with on_success callback."""
        from ledger.gui.dialogs import AccountDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            callback_called = [False]

            def on_success():
                callback_called[0] = True

            dialog = AccountDialog(app, app.manager, on_success)
            assert dialog.on_success is on_success
            assert dialog.manager is app.manager
            assert not callback_called[0], "on_success should not fire on construct"
        finally:
            try:
                dialog.dialog.destroy()
            except Exception:
                pass
            app.destroy()

    def test_account_dialog_closes_cleanly(self, seeded_db: str):
        """AccountDialog closes without error."""
        from ledger.gui.dialogs import AccountDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = AccountDialog(app, app.manager, lambda: None)
            dialog.dialog.destroy()
        finally:
            app.destroy()

    def test_transaction_dialog_constructed(self, seeded_db: str):
        """TransactionDialog can be constructed with on_success callback."""
        from ledger.gui.dialogs import TransactionDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            callback_called = [False]

            def on_success():
                callback_called[0] = True

            dialog = TransactionDialog(app, app.manager, on_success)
            assert dialog.on_success is on_success
            assert dialog.manager is app.manager
            assert not callback_called[0]
        finally:
            try:
                dialog.dialog.destroy()
            except Exception:
                pass
            app.destroy()

    def test_transaction_dialog_closes_cleanly(self, seeded_db: str):
        from ledger.gui.dialogs import TransactionDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = TransactionDialog(app, app.manager, lambda: None)
            dialog.dialog.destroy()
        finally:
            app.destroy()

    def test_buy_sell_dialog_constructed(self, seeded_db: str):
        from ledger.gui.dialogs import BuySellDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            callback_called = [False]

            def on_success():
                callback_called[0] = True

            dialog = BuySellDialog(app, app.manager, on_success)
            assert dialog.on_success is on_success
            assert dialog.manager is app.manager
            assert not callback_called[0]
        finally:
            try:
                dialog.dialog.destroy()
            except Exception:
                pass
            app.destroy()

    def test_buy_sell_dialog_closes_cleanly(self, seeded_db: str):
        from ledger.gui.dialogs import BuySellDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = BuySellDialog(app, app.manager, lambda: None)
            dialog.dialog.destroy()
        finally:
            app.destroy()


# ═══════════════════════════════════════════════════════════════════
#  CRUD THROUGH DIALOG LAUNCHERS
# ═══════════════════════════════════════════════════════════════════


@no_display
class TestCRUDThroughDialogs:
    """Dialog launchers create accounts and transactions correctly."""

    def test_dialog_add_account_called(self, seeded_db: str):
        """_dialog_add_account creates an AccountDialog."""
        import tkinter as tk
        from ledger.gui.dialogs import AccountDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = AccountDialog.__init__
            construct_args = [None]

            def tracked_init(self, parent, manager, on_success,
                             edit_acct=None, edit_acct_id=None):
                construct_args[0] = (parent, manager, on_success, edit_acct, edit_acct_id)
                original(self, parent, manager, on_success,
                         edit_acct=edit_acct, edit_acct_id=edit_acct_id)

            AccountDialog.__init__ = tracked_init
            try:
                app._dialog_add_account()
                assert construct_args[0] is not None
                # Ensure dialog is destroyed if created
                for child in app.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
            finally:
                AccountDialog.__init__ = original
        finally:
            app.destroy()

    def test_dialog_add_transaction_called(self, seeded_db: str):
        """_dialog_add_transaction creates a TransactionDialog."""
        import tkinter as tk
        from ledger.gui.dialogs import TransactionDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = TransactionDialog.__init__
            construct_args = [None]

            def tracked_init(self, parent, manager, on_success,
                             edit_txn=None, edit_txn_id=None):
                construct_args[0] = (parent, manager, on_success, edit_txn, edit_txn_id)
                original(self, parent, manager, on_success,
                         edit_txn=edit_txn, edit_txn_id=edit_txn_id)

            TransactionDialog.__init__ = tracked_init
            try:
                app._dialog_add_transaction()
                assert construct_args[0] is not None
                for child in app.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
            finally:
                TransactionDialog.__init__ = original
        finally:
            app.destroy()

    def test_dialog_buy_sell_called(self, seeded_db: str):
        """_dialog_buy_sell creates a BuySellDialog."""
        import tkinter as tk
        from ledger.gui.dialogs import BuySellDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = BuySellDialog.__init__
            construct_args = [None]

            def tracked_init(self, parent, manager, on_success):
                construct_args[0] = (parent, manager, on_success)
                original(self, parent, manager, on_success)

            BuySellDialog.__init__ = tracked_init
            try:
                app._dialog_buy_sell()
                assert construct_args[0] is not None
                for child in app.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
            finally:
                BuySellDialog.__init__ = original
        finally:
            app.destroy()

    def test_dialog_delete_account_with_children_shows_error(self, seeded_db: str):
        """Deleting an account with children shows error (no dialog)."""
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            # Assets (id=1) has children
            shown = []

            def fake_showerror(title, msg, **kw):
                shown.append(title)

            orig_showerror = mb.showerror
            mb.showerror = fake_showerror

            app._dialog_delete_account(1)
            assert len(shown) > 0
            assert "Cannot Delete" in shown[0]

            mb.showerror = orig_showerror
        finally:
            app.destroy()

    def test_dialog_delete_transaction_works(self, seeded_db: str):
        """_dialog_delete_transaction deletes the transaction."""
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            txn_id = list(app.manager.journal.transactions.keys())[0]
            orig_ask = mb.askyesno
            mb.askyesno = lambda title, msg, **kw: True
            try:
                app._dialog_delete_transaction(txn_id)
                assert txn_id not in app.manager.journal.transactions
            finally:
                mb.askyesno = orig_ask
        finally:
            app.destroy()

    def test_delete_selected_transaction(self, seeded_db: str):
        """_delete_selected_transaction deletes the selected row."""
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            table = app.transaction_table
            first = table.get_children()[0]
            table.selection_set(first)

            orig_ask = mb.askyesno
            mb.askyesno = lambda title, msg, **kw: True
            orig_show = mb.showinfo
            mb.showinfo = lambda title, msg, **kw: None

            try:
                txn_count_before = len(app.manager.journal.transactions)
                app._delete_selected_transaction()
                assert len(app.manager.journal.transactions) == txn_count_before - 1
            finally:
                mb.askyesno = orig_ask
                mb.showinfo = orig_show
        finally:
            app.destroy()

    def test_delete_selected_none_does_nothing(self, seeded_db: str):
        """_delete_selected_transaction with no selection is a no-op."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            before = len(app.manager.journal.transactions)
            app._delete_selected_transaction()
            assert len(app.manager.journal.transactions) == before
        finally:
            app.destroy()


# ═══════════════════════════════════════════════════════════════════
#  KEYBOARD BINDINGS
# ═══════════════════════════════════════════════════════════════════


@no_display
class TestKeyboardBindings:
    """Keyboard shortcuts are properly bound."""

    def test_bind_all_control_n(self, seeded_db: str):
        """Ctrl+N is bound via bind_all."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.bind_all("<Control-n>")
            assert binding is not None and binding != "", \
                "Ctrl+N not bound via bind_all"
        finally:
            app.destroy()

    def test_bind_all_control_t(self, seeded_db: str):
        """Ctrl+T is bound via bind_all."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.bind_all("<Control-t>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()

    def test_bind_all_control_b(self, seeded_db: str):
        """Ctrl+B is bound via bind_all."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.bind_all("<Control-b>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()

    def test_bind_all_control_i(self, seeded_db: str):
        """Ctrl+I is bound via bind_all."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.bind_all("<Control-i>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()

    def test_bind_all_control_q(self, seeded_db: str):
        """Ctrl+Q is bound via bind_all."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.bind_all("<Control-q>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()

    def test_bind_all_f5(self, seeded_db: str):
        """F5 is bound via bind_all."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.bind_all("<F5>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()

    def test_transaction_table_delete_bound(self, seeded_db: str):
        """Delete key is bound on transaction_table."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.transaction_table.bind("<Delete>")
            assert binding is not None and binding != "", \
                "Delete key not bound on transaction table"
        finally:
            app.destroy()

    def test_transaction_table_double_click_bound(self, seeded_db: str):
        """Double-click is bound on transaction_table."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.transaction_table.bind("<Double-1>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()

    def test_account_tree_select_bound(self, seeded_db: str):
        """TreeviewSelect is bound on account_tree."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            binding = app.account_tree.bind("<<TreeviewSelect>>")
            assert binding is not None and binding != ""
        finally:
            app.destroy()
