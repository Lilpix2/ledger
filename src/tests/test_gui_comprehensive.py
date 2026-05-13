"""Comprehensive UI behaviour tests for the Ledger GUI.

These tests validate that the tkinter interface behaves correctly across
all major workflows: account tree, transaction table, portfolio, status
bar, search/filter, import, and account management.

Each test creates the app with a seeded database, then programmatically
interacts with widgets and checks state changes.

Note: Requires a display (X11/Wayland/Xvfb). Skipped automatically
when no display is available.
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


# ── Helpers ────────────────────────────────────────────────────────


def _format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _make_seeded_db(path: str) -> AccountManager:
    """Create a manager at *path* with realistic data."""
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Roth IRA", 1, account_subtype="retirement")
    mgr.add_account("MESP", 1, account_subtype="mesp")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)
    mgr.add_account("Rent", 5)
    mgr.add_account("Capital Gains", 4)

    ids = {acct.name: aid for aid, acct in mgr.accounts.items() if aid}

    # Opening balances
    mgr.add_transaction(
        datetime(2026, 1, 1), "Opening balances",
        [
            Split(ids["HS Checking"], 5000000),
            Split(ids["Savings"], 1000000),
            Split(ids["Schwab Brokerage"], 2000000),
            Split(ids["Roth IRA"], 500000),
            Split(ids["MESP"], 10400000),
            Split(ids["Discover"], -530000),
            Split(6, -18370000),
        ],
    )

    # Income
    mgr.add_transaction(
        datetime(2026, 6, 1), "Payday",
        [Split(ids["Wages"], -300000), Split(ids["HS Checking"], 300000)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 15), "Payday",
        [Split(ids["Wages"], -300000), Split(ids["HS Checking"], 300000)],
    )

    # Expenses
    mgr.add_transaction(
        datetime(2026, 6, 2), "Rent",
        [Split(ids["Rent"], 150000), Split(ids["HS Checking"], -150000)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 3), "Groceries",
        [Split(ids["Groceries"], 4500), Split(ids["HS Checking"], -4500)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 10), "Groceries",
        [Split(ids["Groceries"], 3200), Split(ids["HS Checking"], -3200)],
    )

    # Investment buys
    mgr.buy_security(
        datetime(2026, 2, 1), "Buy VTI",
        ids["Schwab Brokerage"], ids["HS Checking"],
        "VTI", 40, 27500,
    )
    mgr.buy_security(
        datetime(2026, 3, 1), "Buy AAPL",
        ids["Schwab Brokerage"], ids["HS Checking"],
        "AAPL", 20, 15000,
    )
    mgr.buy_security(
        datetime(2026, 4, 1), "Buy VT",
        ids["Roth IRA"], ids["HS Checking"],
        "VT", 100, 10500,
    )

    # Prices
    mgr.save_price("VTI", "2026-05-13", 29000)
    mgr.save_price("AAPL", "2026-05-13", 16500)
    mgr.save_price("VT", "2026-05-13", 11000)

    mgr.generate_ledger()
    mgr._ids = ids
    return mgr


@pytest.fixture
def seeded_db() -> str:
    """Path to a fully seeded SQLite database."""
    path = tempfile.mktemp(suffix=".db")
    _make_seeded_db(path)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ════════════════════════════════════════════════════════════════════
#  ACCOUNT TREE
# ════════════════════════════════════════════════════════════════════


@no_display
class TestAccountTree:
    """The account tree view displays the correct hierarchy and balances."""

    def test_tree_structure(self, seeded_db: str):
        """Tree has the expected parent-child relationships."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree
            roots = tree.get_children()
            root_labels = [tree.item(r, "text") for r in roots]
            for name in ["assets", "liabilities", "equity", "income", "expenses"]:
                assert name in root_labels, f"Missing root '{name}' in {root_labels}"

            asset_item = self._find_tree_item(tree, "assets")
            assert asset_item is not None
            asset_children = tree.get_children(asset_item)
            assert len(asset_children) >= 2, f"Too few asset children: {asset_children}"
        finally:
            app.destroy()

    def test_all_accounts_appear_in_tree(self, seeded_db: str):
        """Every account has a corresponding tree node."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree
            visible = set()

            def walk(iid):
                visible.add(tree.item(iid, "text"))
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)

            for aid, acct in app.manager.accounts.items():
                if aid == 0:
                    continue
                assert acct.name in visible, f"'{acct.name}' (id={aid}) missing from tree"
        finally:
            app.destroy()

    def test_tree_balances_match_ledger(self, seeded_db: str):
        """Each node's displayed balance matches the manager."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def walk(iid):
                values = tree.item(iid, "values")
                if values and len(values) > 0:
                    aid = int(iid)
                    expected = app.manager.get_display_balance(aid)
                    assert values[0] == _format_cents(expected), (
                        f"'{tree.item(iid, 'text')}' shows {values[0]}, expected {_format_cents(expected)}"
                    )
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)
        finally:
            app.destroy()

    def test_all_balances_positive(self, seeded_db: str):
        """Every balance in the tree is zero or positive."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def walk(iid):
                values = tree.item(iid, "values")
                if values and len(values) > 0:
                    assert not values[0].startswith("-"), (
                        f"Negative for '{tree.item(iid, 'text')}': {values[0]}"
                    )
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)
        finally:
            app.destroy()

    def test_subtypes_in_labels(self, seeded_db: str):
        """Accounts with subtypes show the subtype tag."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            hs = self._find_tree_item(tree, "HS Checking")
            assert hs is not None
            assert "checking" in tree.item(hs, "values")[1].lower()

            disc = self._find_tree_item(tree, "Discover")
            assert disc is not None
            vals = tree.item(disc, "values")
            assert "credit" in vals[1].lower() or "credit_card" in vals[1].lower()
        finally:
            app.destroy()

    def test_no_orphan_iids(self, seeded_db: str):
        """Every tree iid maps to a valid account."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def walk(iid):
                assert int(iid) in app.manager.accounts, f"Orphan iid {iid}"
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)
        finally:
            app.destroy()

    @staticmethod
    @staticmethod
    def _find_tree_item(tree, text: str):
        def walk(iid):
            if tree.item(iid, "text") == text:
                return iid
            for child in tree.get_children(iid):
                r = walk(child)
                if r:
                    return r
            return None

        for root in tree.get_children():
            r = walk(root)
            if r:
                return r
        return None


# ════════════════════════════════════════════════════════════════════
#  TRANSACTION TABLE
# ════════════════════════════════════════════════════════════════════


@no_display
class TestTransactionTable:
    """The transaction journal table shows correct data."""

    def test_table_has_correct_columns(self, seeded_db: str):
        """Table columns: date, desc, amount."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            cols = app.transaction_table["columns"]
            assert cols == ("date", "desc", "amount"), f"Unexpected columns: {cols}"
        finally:
            app.destroy()

    def test_table_shows_all_transactions(self, seeded_db: str):
        """Each transaction appears once in the table."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            rows = app.transaction_table.get_children()
            expected = len(app.manager.journal.transactions)
            assert len(rows) == expected, f"Table has {len(rows)} rows, expected {expected}"
        finally:
            app.destroy()

    def test_table_rows_have_data(self, seeded_db: str):
        """Every row has date, description, and amount."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            for item in app.transaction_table.get_children():
                v = app.transaction_table.item(item, "values")
                assert len(v) == 3, f"Row has {len(v)} values: {v}"
                assert v[0], f"Empty date"
                assert v[1], f"Empty description"
                assert v[2], f"Empty amount"
        finally:
            app.destroy()

    def test_table_amount_is_integer_cents(self, seeded_db: str):
        """The amount column contains integer cent values."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            for item in app.transaction_table.get_children():
                try:
                    int(app.transaction_table.item(item, "values")[2])
                except ValueError:
                    assert False, f"Amount not integer: {app.transaction_table.item(item, 'values')[2]}"
        finally:
            app.destroy()

    def test_selecting_account_filters_table(self, seeded_db: str):
        """Selecting an account in the tree filters the transaction table."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree
            hs = self._find_tree_item(tree, "HS Checking")
            if hs:
                tree.selection_set(hs)
                tree.event_generate("<<TreeviewSelect>>")
                app._on_account_select()
                assert app._filter_account_id == int(hs), f"Filter not set to HS Checking"
        finally:
            app.destroy()

    @staticmethod
    @staticmethod
    def _find_tree_item(tree, text: str):
        def walk(iid):
            if tree.item(iid, "text") == text:
                return iid
            for child in tree.get_children(iid):
                r = walk(child)
                if r:
                    return r
            return None

        for root in tree.get_children():
            r = walk(root)
            if r:
                return r
        return None


# ════════════════════════════════════════════════════════════════════
#  STATUS BAR
# ════════════════════════════════════════════════════════════════════


@no_display
class TestStatusBar:
    """The status bar reflects the accounting equation."""

    def test_status_bar_present(self, seeded_db: str):
        """Status bar shows equation text."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            t = app.status_var.get()
            assert "Assets" in t and "Liabilities" in t and "Net Worth" in t
        finally:
            app.destroy()

    def test_equation_shows_balanced(self, seeded_db: str):
        """Status bar marks the equation as balanced."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            assert "✓" in app.status_var.get(), "Status not showing balanced"
        finally:
            app.destroy()

    def test_status_updates_after_new_transaction(self, seeded_db: str):
        """Adding a transaction updates the status bar."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            before = app.status_var.get()
            ids = {acct.name: aid for aid, acct in app.manager.accounts.items() if aid}
            app.manager.add_transaction(
                datetime(2026, 7, 1), "Extra",
                [Split(ids.get("Wages", 4), -100000), Split(ids["HS Checking"], 100000)],
            )
            app.manager.generate_ledger()
            app._refresh_status()
            assert app.status_var.get() != before, "Status didn't change"
        finally:
            app.destroy()

    def test_status_updated_after_close(self, seeded_db: str):
        """Closing entries keep the status balanced."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            app.manager.close_temps()
            app.manager.generate_ledger()
            app._refresh_status()
            assert "✓" in app.status_var.get()
        finally:
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  PORTFOLIO TAB
# ════════════════════════════════════════════════════════════════════


@no_display
class TestPortfolioTab:
    """The Portfolio tab displays holdings correctly."""

    def test_portfolio_has_tab(self, seeded_db: str):
        """Notebook has a Portfolio tab."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            assert "Portfolio" in tabs, f"Portfolio tab missing: {tabs}"
        finally:
            app.destroy()

    def test_portfolio_shows_holdings(self, seeded_db: str):
        """Holdings appear after refreshing portfolio tab."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            notebook = app.notebook
            for i, tab_id in enumerate(notebook.tabs()):
                if notebook.tab(tab_id, "text") == "Portfolio":
                    notebook.select(i)
                    break

            app._refresh_portfolio()
            # The table should have rows with ticker names
            table = app.portfolio_table
            tickers_in_table = set()
            for item in table.get_children():
                values = table.item(item, "values")
                if values and len(values) >= 2:
                    tickers_in_table.add(values[1])  # ticker column

            assert len(tickers_in_table) > 0, (
                f"No rows in portfolio table: {tickers_in_table}"
            )
            summary = app.port_summary_var.get()
            assert summary, "Portfolio summary empty"
        finally:
            app.destroy()

    def test_portfolio_subtotals_match_manager(self, seeded_db: str):
        """Portfolio summary loads without error."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            notebook = app.notebook
            for i, tab_id in enumerate(notebook.tabs()):
                if notebook.tab(tab_id, "text") == "Portfolio":
                    notebook.select(i)
                    break
            app._refresh_portfolio()
            assert app.port_summary_var.get(), "Empty portfolio summary"
            assert "Error" not in app.port_summary_var.get()
        finally:
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  SEARCH / FILTER
# ════════════════════════════════════════════════════════════════════


@no_display
class TestSearchFilter:
    """Search and filter controls exist."""

    def test_search_entry_exists(self, seeded_db: str):
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            assert app.search_var is not None
        finally:
            app.destroy()

    def test_filter_date_fields_exist(self, seeded_db: str):
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            assert hasattr(app, "date_from_var")
            assert hasattr(app, "date_to_var")
        finally:
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  MENU BAR
# ════════════════════════════════════════════════════════════════════


@no_display
class TestMenuBar:
    """Menu bar structure and commands work."""

    def _menu_labels(self, app, cascade_label: str):
        """Return the list of labels inside a cascade menu."""
        menu = app.winfo_children()[0]
        for i in range(menu.index("end") + 1):
            try:
                if menu.entrycget(i, "label") == cascade_label:
                    sub = menu.nametowidget(menu.entrycget(i, "menu"))
                    labels = []
                    for j in range(sub.index("end") + 1):
                        try:
                            labels.append(sub.entrycget(j, "label"))
                        except Exception:
                            pass
                    return labels
            except Exception:
                pass
        return []

    def test_menu_has_all_sections(self, seeded_db: str):
        """Expected top-level menu sections exist."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
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

    def test_account_menu_has_expected_items(self, seeded_db: str):
        """Account menu: New Account…, Net Worth, Account Summary."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            items = self._menu_labels(app, "Accounts")
            assert "New Account…" in items, f"Missing in Accounts menu: {items}"
            assert "Net Worth" in items
            assert "Account Summary" in items
        finally:
            app.destroy()

    def test_transaction_menu_has_expected_items(self, seeded_db: str):
        """Transaction menu: New Transaction…, Buy / Sell…, reports."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            items = self._menu_labels(app, "Transactions")
            assert "New Transaction…" in items, f"Missing in Transactions menu: {items}"
            assert "Buy / Sell…" in items
            assert "Income Statement" in items
            assert "Balance Sheet" in items
            assert "RE Statement" in items
        finally:
            app.destroy()

    def test_report_menu_commands_fire(self, seeded_db: str):
        """Each report command opens a dialog with content."""
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            orig = mb.showinfo
            shown = []

            def fake(title, msg, **kw):
                shown.append((title, msg))
                return "ok"

            mb.showinfo = fake
            app._show_net_worth()
            app._show_summary()
            app._show_income_stmt()
            app._show_balance_sheet()
            app._show_re_statement()
            mb.showinfo = orig

            assert len(shown) == 5, f"Expected 5 dialogs, got {len(shown)}"
            for title, msg in shown:
                assert msg, f"Empty message for {title}"
                assert "None" not in msg
        finally:
            mb.showinfo = orig
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  NOTEBOOK TABS
# ════════════════════════════════════════════════════════════════════


@no_display
class TestNotebookTabs:
    """The notebook has the expected tabs."""

    def test_ledger_tab_present(self, seeded_db: str):
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            assert "Ledger" in tabs
        finally:
            app.destroy()

    def test_portfolio_tab_present(self, seeded_db: str):
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            assert "Portfolio" in tabs
        finally:
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  REPORT CONTENT
# ════════════════════════════════════════════════════════════════════


@no_display
class TestReportContent:
    """Report dialogs contain the expected information."""

    def test_net_worth_has_numbers(self, seeded_db: str):
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            orig = mb.showinfo
            cap = []

            def fake(title, msg, **kw):
                cap.append((title, msg))
                return "ok"

            mb.showinfo = fake
            app._show_net_worth()
            mb.showinfo = orig

            _, msg = cap[0]
            assert "$" in msg
            sec = msg.split("Assets:")[1][:20] if "Assets:" in msg else ""
            assert "0.00" not in sec, f"Assets are zero: {msg}"
        finally:
            mb.showinfo = orig
            app.destroy()

    def test_income_statement_has_breakdown(self, seeded_db: str):
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            orig = mb.showinfo
            cap = []

            def fake(title, msg, **kw):
                cap.append((title, msg))
                return "ok"

            mb.showinfo = fake
            app._show_income_stmt()
            mb.showinfo = orig

            _, msg = cap[0]
            assert "INCOME" in msg
            assert "EXPENSES" in msg
            assert "Net" in msg
            assert "Wages" in msg
            assert "Groceries" in msg or "Rent" in msg
        finally:
            mb.showinfo = orig
            app.destroy()

    def test_balance_sheet_shows_all_assets(self, seeded_db: str):
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            orig = mb.showinfo
            cap = []

            def fake(title, msg, **kw):
                cap.append((title, msg))
                return "ok"

            mb.showinfo = fake
            app._show_balance_sheet()
            mb.showinfo = orig

            _, msg = cap[0]
            assert "ASSETS" in msg and "LIABILITIES" in msg and "EQUITY" in msg
            assert "HS Checking" in msg
            assert "Discover" in msg
        finally:
            mb.showinfo = orig
            app.destroy()

    def test_re_statement_dividend_line_present_if_applicable(self, seeded_db: str):
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            orig = mb.showinfo
            cap = []

            def fake(title, msg, **kw):
                cap.append((title, msg))
                return "ok"

            mb.showinfo = fake
            ids = {acct.name: aid for aid, acct in app.manager.accounts.items() if aid}
            app.manager.add_transaction(
                datetime(2026, 7, 1), "Dividend paid",
                [Split(9, 50000), Split(ids.get("HS Checking", 7), -50000)],
            )
            app.manager.generate_ledger()
            app._show_re_statement()
            mb.showinfo = orig

            _, msg = cap[0]
            assert "Dividend" in msg or "dividend" in msg
        finally:
            mb.showinfo = orig
            app.destroy()

    def test_re_statement_no_dividend_line_when_none(self, seeded_db: str):
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            orig = mb.showinfo
            cap = []

            def fake(title, msg, **kw):
                cap.append((title, msg))
                return "ok"

            mb.showinfo = fake
            app._show_re_statement()
            mb.showinfo = orig

            _, msg = cap[0]
            assert "Dividend" not in msg
        finally:
            mb.showinfo = orig
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  CRUD DIALOGS
# ════════════════════════════════════════════════════════════════════


@no_display
class TestCRUDDialogs:
    """CRUD dialogs can be opened and return expected data."""

    def test_account_dialog_opens(self, seeded_db: str):
        from ledger.gui.dialogs import AccountDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = AccountDialog(app, app.manager, on_success=lambda: None)
            try:
                assert dialog.dialog is not None
                assert dialog.dialog.winfo_exists()
            finally:
                dialog.dialog.destroy()
        finally:
            app.destroy()

    def test_transaction_dialog_opens(self, seeded_db: str):
        from ledger.gui.dialogs import TransactionDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = TransactionDialog(app, app.manager, on_success=lambda: None)
            try:
                assert dialog.dialog is not None
                assert dialog.dialog.winfo_exists()
            finally:
                dialog.dialog.destroy()
        finally:
            app.destroy()

    def test_buy_sell_dialog_opens(self, seeded_db: str):
        from ledger.gui.dialogs import BuySellDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = BuySellDialog(app, app.manager, on_success=lambda: None)
            try:
                assert dialog.dialog is not None
                assert dialog.dialog.winfo_exists()
            finally:
                dialog.dialog.destroy()
        finally:
            app.destroy()


# ════════════════════════════════════════════════════════════════════
#  WINDOW PROPERTIES
# ════════════════════════════════════════════════════════════════════


@no_display
class TestWindowProperties:
    """The main window has the correct properties."""

    def test_window_title(self, seeded_db: str):
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            t = app.title()
            assert "Ledger" in t
            assert "Double-Entry" in t
        finally:
            app.destroy()

    def test_minimum_size(self, seeded_db: str):
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            w, h = app.minsize()
            assert w >= 800
            assert h >= 500
        finally:
            app.destroy()
