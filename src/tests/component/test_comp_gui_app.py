"""Component tests: LedgerGUI widget structure.

Tests the structural/visual aspects of the GUI using a temporary SQLite
database (fast setup, no shared state). These replace heavier E2E tests
that only check widget existence and basic structure.

Each test:
1. Creates a temp DB
2. Seeds with minimal accounts
3. Creates LedgerGUI with that DB
4. Checks the widget structure
5. Destroys the app and cleans up

Requires a display (X11/Wayland/Xvfb). Skipped when not available.
"""

import os
import tempfile

import pytest

from ledger.controllers.accounts import AccountManager
from datetime import datetime
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
                try:
                    root.destroy()
                except Exception:
                    pass
        except Exception:
            pass


# ── Seeded DB builder ─────────────────────────────────────────────


def _build_temp_db() -> str:
    """Create a temp SQLite DB with minimal seeded data and return path."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)

    ids = {acct.name: aid for aid, acct in mgr.accounts.items() if aid}

    mgr.add_transaction(
        datetime(2026, 1, 1), "Opening balances",
        [
            Split(ids["HS Checking"], 5000000),
            Split(ids["Savings"], 1000000),
            Split(ids["Schwab Brokerage"], 2000000),
            Split(ids["Discover"], -530000),
            Split(6, -7470000),
        ],
    )
    mgr.add_transaction(
        datetime(2026, 6, 1), "Payday",
        [Split(ids["Wages"], -300000), Split(ids["HS Checking"], 300000)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 2), "Groceries",
        [Split(ids["Groceries"], 4500), Split(ids["HS Checking"], -4500)],
    )

    mgr.generate_ledger()
    del mgr
    return path


def _build_portfolio_db() -> str:
    """Create a temp DB seeded with accounts that have holdings/investments."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Capital Gains", 4)

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

    mgr.buy_security(
        datetime(2026, 2, 1), "Buy VTI",
        ids["Schwab Brokerage"], ids["HS Checking"],
        "VTI", 100, 27500,
    )
    mgr.buy_security(
        datetime(2026, 3, 1), "Buy AAPL",
        ids["Schwab Brokerage"], ids["HS Checking"],
        "AAPL", 50, 15000,
    )

    mgr.save_price("VTI", "2026-05-13", 29000)
    mgr.save_price("AAPL", "2026-05-13", 16500)

    mgr.generate_ledger()
    del mgr
    return path


# ════════════════════════════════════════════════════════════════════
#  GUI STRUCTURE
# ════════════════════════════════════════════════════════════════════


@no_display
class TestGUIStructure:
    """LedgerGUI constructs with the correct widget structure."""

    def test_constructs_without_errors(self):
        """LedgerGUI can be created with a temp DB without raising."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            assert app is not None
            assert app.manager is not None
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_account_tree_has_five_roots(self):
        """Account tree has 5 root items: Assets, Liabilities, Equity, Income, Expenses."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            tree = app.account_tree
            roots = tree.get_children()
            root_labels = [tree.item(r, "text") for r in roots]
            for name in ["assets", "liabilities", "equity", "income", "expenses"]:
                assert name in root_labels, f"Missing root '{name}' in {root_labels}"
            assert len(roots) == 5, f"Expected 5 roots, got {len(roots)}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_account_tree_root_children_have_accounts(self):
        """Non-root accounts appear as children of the root tree items."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            tree = app.account_tree

            # Build set of all visible text labels
            def _visible_labels(iid):
                labels = {tree.item(iid, "text")}
                for child in tree.get_children(iid):
                    labels |= _visible_labels(child)
                return labels

            all_visible = set()
            for root in tree.get_children():
                all_visible |= _visible_labels(root)

            # Check a few specific accounts
            for name in ["HS Checking", "Savings", "Discover", "Wages", "Groceries"]:
                assert name in all_visible, f"'{name}' not visible in tree"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_window_title(self):
        """Window title is correct."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            t = app.title()
            assert "Ledger" in t
            assert "Double-Entry" in t
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_minimum_size(self):
        """Window minimum size is at least 800x500."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            w, h = app.minsize()
            assert w >= 800, f"Min width {w} < 800"
            assert h >= 500, f"Min height {h} < 500"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_notebook_has_two_tabs(self):
        """Notebook has Ledger and Portfolio tabs."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            assert "Ledger" in tabs, f"Ledger tab missing: {tabs}"
            assert "Portfolio" in tabs, f"Portfolio tab missing: {tabs}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_menu_bar_has_cascades(self):
        """Menu bar has File, Accounts, Transactions, Help menus."""
        import tkinter as tk
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            menu = app.winfo_children()[0]
            found = set()
            for i in range(menu.index("end") + 1):
                try:
                    found.add(menu.entrycget(i, "label"))
                except Exception:
                    pass
            for name in ["File", "Accounts", "Transactions", "Help"]:
                assert name in found, f"Menu '{name}' missing: {found}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_status_bar_exists_and_balanced(self):
        """Status bar shows accounting equation with balanced mark."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            t = app.status_var.get()
            assert "Assets" in t, f"Status missing Assets: {t}"
            assert "Liabilities" in t, f"Status missing Liabilities: {t}"
            assert "Net Worth" in t, f"Status missing Net Worth: {t}"
            assert "✓" in t, f"Status not showing balanced: {t}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_search_filter_vars_exist(self):
        """Search and filter variables are created."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            assert app.search_var is not None, "search_var is None"
            assert hasattr(app, "date_from_var"), "Missing date_from_var"
            assert hasattr(app, "date_to_var"), "Missing date_to_var"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_keyboard_shortcuts_are_callable(self):
        """Core shortcut handler methods exist and are callable."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            assert callable(app._refresh_all), "_refresh_all not callable"
            assert callable(app._dialog_add_account), "_dialog_add_account not callable"
            assert callable(app._dialog_add_transaction), "_dialog_add_transaction not callable"
            assert callable(app._dialog_buy_sell), "_dialog_buy_sell not callable"
            assert callable(app._on_close), "_on_close not callable"
            assert callable(app._dialog_import_qif), "_dialog_import_qif not callable"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_portfolio_tab_populates(self):
        """Portfolio tab populates correctly when holdings exist."""
        db_path = _build_portfolio_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            # Find and switch to portfolio tab
            notebook = app.notebook
            for i, tab_id in enumerate(notebook.tabs()):
                if notebook.tab(tab_id, "text") == "Portfolio":
                    notebook.select(i)
                    break

            app._refresh_portfolio()

            # Portfolio table should have rows
            table = app.portfolio_table
            tickers_in_table = set()
            for item in table.get_children():
                values = table.item(item, "values")
                if values and len(values) >= 2:
                    tickers_in_table.add(values[1])

            assert len(tickers_in_table) > 0, "No tickers in portfolio table"
            summary = app.port_summary_var.get()
            assert summary, "Portfolio summary is empty"
            assert "Error" not in summary, f"Error in portfolio summary: {summary}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_transaction_table_has_correct_columns(self):
        """Transaction table columns: date, desc, amount."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            cols = app.transaction_table["columns"]
            assert cols == ("date", "desc", "amount"), f"Unexpected columns: {cols}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_transaction_table_has_rows(self):
        """Transaction table has the expected number of rows."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            rows = app.transaction_table.get_children()
            expected = len(app.manager.journal.transactions)
            assert len(rows) == expected, f"Expected {expected} rows, got {len(rows)}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_transaction_table_rows_have_data(self):
        """Every row has date, description, and amount."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            for item in app.transaction_table.get_children():
                v = app.transaction_table.item(item, "values")
                assert len(v) == 3, f"Row has {len(v)} values: {v}"
                assert v[0], "Empty date"
                assert v[1], "Empty description"
                assert v[2], "Empty amount"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_equation_balanced_after_construction(self):
        """Accounting equation is balanced right after construction."""
        db_path = _build_temp_db()
        from ledger.gui_app import LedgerGUI
        app = LedgerGUI(db_path=db_path)
        try:
            eq = app.manager.check_accounting_equation()
            assert eq["balanced"], f"Equation unbalanced on construction: {eq}"
        finally:
            app.destroy()
            try:
                os.unlink(db_path)
            except OSError:
                pass
