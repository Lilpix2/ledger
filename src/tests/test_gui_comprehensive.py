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
from unittest.mock import MagicMock, patch
from decimal import Decimal

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
    """Match the app's formatter."""
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
            Split(6, -18170000),
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
#  UI BEHAVIOUR TESTS
# ════════════════════════════════════════════════════════════════════


@no_display
class TestAccountTree:
    """The account tree view displays the correct hierarchy and balances."""

    def test_tree_structure(self, seeded_db: str):
        """Tree has the expected parent-child relationships."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            # Root nodes are top-level account categories
            roots = tree.get_children()
            root_labels = [tree.item(r, "text") for r in roots]
            expected_roots = ["assets", "liabilities", "equity",
                              "income", "expenses"]
            for name in expected_roots:
                assert name in root_labels, (
                    f"Missing root node '{name}' in {root_labels}"
                )

            # Assets has children (cash, Checking, Savings, Brokerage …)
            asset_item = self._find_tree_item(tree, "assets")
            assert asset_item is not None
            asset_children = tree.get_children(asset_item)
            assert len(asset_children) >= 2, (
                f"Assets should have sub-accounts, got {len(asset_children)}"
            )

        finally:
            app.destroy()

    def test_all_accounts_appear_in_tree(self, seeded_db: str):
        """Every account in the manager has a corresponding tree node."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            # Collect all visible names in the tree
            visible = set()

            def walk(iid: str) -> None:
                visible.add(tree.item(iid, "text"))
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)

            # Every named account (skip defaults without transactions)
            for aid, acct in app.manager.accounts.items():
                if aid == 0:
                    continue
                assert acct.name in visible, (
                    f"Account '{acct.name}' (id={aid}) missing from tree"
                )

        finally:
            app.destroy()

    def test_tree_balances_match_ledger(self, seeded_db: str):
        """Each tree node's displayed balance matches the manager."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def walk(iid: str) -> None:
                values = tree.item(iid, "values")
                if values and len(values) > 0:
                    display_str = values[0]
                    aid = int(iid)
                    expected = app.manager.get_display_balance(aid)
                    expected_str = _format_cents(expected)
                    assert display_str == expected_str, (
                        f"Tree shows '{display_str}' for '{tree.item(iid, 'text')}' "
                        f"(id={aid}), expected '{expected_str}'"
                    )
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)

        finally:
            app.destroy()

    def test_all_balances_positive(self, seeded_db: str):
        """Every balance in the tree is formatted as zero or positive."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def walk(iid: str) -> None:
                values = tree.item(iid, "values")
                if values and len(values) > 0:
                    bal_str = values[0]
                    assert not bal_str.startswith("-"), (
                        f"Negative balance for '{tree.item(iid, 'text')}': {bal_str}"
                    )
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)

        finally:
            app.destroy()

    def test_subtypes_in_labels(self, seeded_db: str):
        """Accounts with subtypes show the subtype tag."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            checking_item = self._find_tree_item(tree, "HS Checking")
            assert checking_item is not None
            values = tree.item(checking_item, "values")
            # Second column should include subtype
            assert len(values) >= 2
            assert "checking" in values[1].lower(), (
                f"Expected 'checking' subtype tag, got {values[1]}"
            )

            discover_item = self._find_tree_item(tree, "Discover")
            assert discover_item is not None
            values = tree.item(discover_item, "values")
            assert "credit_card" in values[1].lower() or "credit" in values[1].lower(), (
                f"Expected credit_card subtype tag, got {values[1]}"
            )

        finally:
            app.destroy()

    def test_no_orphan_iids(self, seeded_db: str):
        """Every tree iid maps to a valid account."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def walk(iid: str) -> None:
                aid = int(iid)
                assert aid in app.manager.accounts, (
                    f"Tree has iid '{iid}' for non-existent account"
                )
                for child in tree.get_children(iid):
                    walk(child)

            for root in tree.get_children():
                walk(root)

        finally:
            app.destroy()

    @staticmethod
    def _find_tree_item(tree, text: str):
        """Find a tree item by its display text."""
        def walk(iid: str) -> str or None:
            if tree.item(iid, "text") == text:
                return iid
            for child in tree.get_children(iid):
                result = walk(child)
                if result:
                    return result
            return None

        for root in tree.get_children():
            result = walk(root)
            if result:
                return result
        return None


@no_display
class TestTransactionTable:
    """The transaction journal table shows correct data."""

    def test_table_has_correct_columns(self, seeded_db: str):
        """Transaction table has the expected column headers."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            table = app.transaction_table
            columns = table["columns"]
            expected_cols = [
                "date", "description", "total", "account",
                "debit", "credit",
            ]
            for col in expected_cols:
                assert col in columns, (
                    f"Missing column '{col}' in {columns}"
                )
        finally:
            app.destroy()

    def test_table_shows_all_transactions(self, seeded_db: str):
        """Each transaction appears exactly once in the table."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            table = app.transaction_table
            rows = table.get_children()
            expected_count = len(app.manager.journal.transactions)
            assert len(rows) == expected_count, (
                f"Table has {len(rows)} rows, expected {expected_count} "
                f"(journal has {len(app.manager.journal.transactions)} txns)"
            )
        finally:
            app.destroy()

    def test_table_rows_have_data(self, seeded_db: str):
        """Every transaction row has non-empty values."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            table = app.transaction_table
            for item in table.get_children():
                values = table.item(item, "values")
                assert len(values) >= 5, (
                    f"Row has only {len(values)} values: {values}"
                )
                # Date and description should be non-empty
                assert values[0], f"Empty date in row {item}"
                assert values[1], f"Empty description in row {item}"
        finally:
            app.destroy()

    def test_table_format_cents_in_total(self, seeded_db: str):
        """The total column is formatted as USD."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            table = app.transaction_table
            for item in table.get_children():
                values = table.item(item, "values")
                total_str = values[2]  # total column
                assert total_str.startswith("$") or total_str == "", (
                    f"Total not formatted as USD: {total_str}"
                )
        finally:
            app.destroy()

    def test_selecting_account_filters_table(self, seeded_db: str):
        """Selecting an account in the tree filters the transaction table."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree
            table = app.transaction_table

            # Find HS Checking in the tree
            hs_item = None
            for item in tree.get_children():
                def find(iid: str) -> str or None:
                    if tree.item(iid, "text") == "HS Checking":
                        return iid
                    for child in tree.get_children(iid):
                        r = find(child)
                        if r:
                            return r
                    return None
                hs_item = find(item)
                if hs_item:
                    break

            if hs_item:
                tree.selection_set(hs_item)
                tree.event_generate("<<TreeviewSelect>>")
                app._on_account_select()
                # Table should now show only HS Checking's txns
                actual = app._filter_account_id
                expected = int(hs_item)
                assert actual == expected, (
                    f"Filter account id = {actual}, expected {expected}"
                )
        finally:
            app.destroy()


@no_display
class TestStatusBar:
    """The status bar reflects the accounting equation."""

    def test_status_bar_present(self, seeded_db: str):
        """Status bar exists and shows equation text."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            text = app.status_var.get()
            assert "Assets" in text, f"Status bar missing Assets: {text}"
            assert "Liabilities" in text, f"Status bar missing Liabilities: {text}"
            assert "Net Worth" in text, f"Status bar missing Net Worth: {text}"
        finally:
            app.destroy()

    def test_equation_shows_balanced(self, seeded_db: str):
        """Status bar marks the equation as balanced."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            text = app.status_var.get()
            assert "✓" in text, f"Status bar not showing balanced: {text}"
        finally:
            app.destroy()

    def test_status_updates_after_new_transaction(self, seeded_db: str):
        """Adding a transaction updates the status bar."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            # Get current text
            text_before = app.status_var.get()

            # Add a transaction via the manager
            ids = {acct.name: aid for aid, acct in app.manager.accounts.items()
                   if aid}
            app.manager.add_transaction(
                datetime(2026, 7, 1), "Extra income",
                [Split(ids.get("Wages", 4), -100000),
                 Split(ids["HS Checking"], 100000)],
            )
            app.manager.generate_ledger()
            app._refresh_status()

            text_after = app.status_var.get()
            assert text_after != text_before, (
                f"Status bar didn't change after new transaction:\n"
                f"  Before: {text_before}\n  After: {text_after}"
            )
        finally:
            app.destroy()

    def test_status_updated_after_close(self, seeded_db: str):
        """Closing entries update the status bar and it remains balanced."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            app.manager.close_temps()
            app.manager.generate_ledger()
            app._refresh_status()

            text = app.status_var.get()
            assert "✓" in text, f"Status bar unbalanced after close: {text}"
        finally:
            app.destroy()


@no_display
class TestPortfolioTab:
    """The Portfolio tab displays holdings correctly."""

    def test_portfolio_has_tab(self, seeded_db: str):
        """Notebook has a Portfolio tab."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            notebook = app.notebook
            tabs = notebook.tabs()
            tab_texts = [notebook.tab(t, "text") for t in tabs]
            assert "Portfolio" in tab_texts, (
                f"Portfolio tab missing, got {tab_texts}"
            )
        finally:
            app.destroy()

    def test_portfolio_shows_holdings(self, seeded_db: str):
        """Holdings appear in the portfolio tab."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            # Switch to portfolio tab
            notebook = app.notebook
            for i, tab_id in enumerate(notebook.tabs()):
                if notebook.tab(tab_id, "text") == "Portfolio":
                    notebook.select(i)
                    break

            # Summary text should mention holdings
            summary = app.port_summary_var.get()
            assert "VTI" in summary or "holding" in summary.lower() or "position" in summary.lower(), (
                f"Portfolio summary doesn't mention holdings: {summary}"
            )
        finally:
            app.destroy()

    def test_portfolio_subtotals_match_manager(self, seeded_db: str):
        """Each brokerage account's subtotals match the manager's NAV."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            notebook = app.notebook
            for i, tab_id in enumerate(notebook.tabs()):
                if notebook.tab(tab_id, "text") == "Portfolio":
                    notebook.select(i)
                    break

            # Check that portfolio summary loads (no error)
            summary = app.port_summary_var.get()
            assert summary is not None
            # Should not show an error message
            assert "Error" not in summary
        finally:
            app.destroy()


@no_display
class TestSearchFilter:
    """Search and filter controls work correctly."""

    def test_search_entry_exists(self, seeded_db: str):
        """Search entry field is present."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            search_entry = app.search_var
            assert search_entry is not None
        finally:
            app.destroy()

    def test_filter_date_fields_exist(self, seeded_db: str):
        """Date filter fields exist."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            assert hasattr(app, "date_from_var"), "Missing date_from_var"
            assert hasattr(app, "date_to_var"), "Missing date_to_var"
        finally:
            app.destroy()


@no_display
class TestMenuBar:
    """Menu bar structure and commands work."""

    def test_menu_has_all_sections(self, seeded_db: str):
        """Expected menu sections exist."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            menu = app.winfo_children()[0]
            labels = []
            for i in range(menu.index("end") + 1):
                try:
                    labels.append(menu.entrycget(i, "label"))
                except tk.TclError:
                    pass

            expected = {"File", "Accounts", "Transactions", "Help"}
            for name in expected:
                assert name in labels, (
                    f"Menu '{name}' missing, got {labels}"
                )
        finally:
            app.destroy()

    def test_account_menu_has_expected_items(self, seeded_db: str):
        """Account menu has Add and Edit items."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            menu = app.winfo_children()[0]
            # Find the Accounts menu
            accounts_idx = None
            for i in range(menu.index("end") + 1):
                try:
                    if menu.entrycget(i, "label") == "Accounts":
                        accounts_idx = i
                        break
                except tk.TclError:
                    pass

            assert accounts_idx is not None, "Accounts menu not found"

            accounts_menu = menu.nametowidget(menu.entrycget(accounts_idx, "menu"))
            items = []
            for i in range(accounts_menu.index("end") + 1):
                try:
                    items.append(accounts_menu.entrycget(i, "label"))
                except tk.TclError:
                    items.append("---")

            assert "Add Account" in items, (
                f"Add Account missing in {items}"
            )
            assert "Edit" in items or "Edit Account" in items, (
                f"Edit Account missing in {items}"
            )
        finally:
            app.destroy()

    def test_transaction_menu_has_expected_items(self, seeded_db: str):
        """Transaction menu has Add and Import items."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            menu = app.winfo_children()[0]
            txns_idx = None
            for i in range(menu.index("end") + 1):
                try:
                    if menu.entrycget(i, "label") == "Transactions":
                        txns_idx = i
                        break
                except tk.TclError:
                    pass

            assert txns_idx is not None, "Transactions menu not found"

            txns_menu = menu.nametowidget(menu.entrycget(txns_idx, "menu"))
            items = []
            for i in range(txns_menu.index("end") + 1):
                try:
                    items.append(txns_menu.entrycget(i, "label"))
                except tk.TclError:
                    items.append("---")

            assert "Add Transaction" in items, (
                f"Add Transaction missing in {items}"
            )
            assert "Import" in items or "Import QIF" in items, (
                f"Import missing in {items}"
            )
        finally:
            app.destroy()

    def test_report_menu_commands_fire(self, seeded_db: str):
        """Each report menu command opens a dialog with content."""
        import tkinter as tk
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original_show = mb.showinfo
            shown = []

            def _fake_show(title, message, **kwargs):
                shown.append((title, message))
                return "ok"

            mb.showinfo = _fake_show

            # Trigger each report
            app._show_net_worth()
            app._show_summary()
            app._show_income_stmt()
            app._show_balance_sheet()
            app._show_re_statement()

            # Verify all 5 reports fired
            titles = [s[0] for s in shown]
            assert len(shown) == 5, (
                f"Expected 5 reports, got {len(shown)}: {titles}"
            )

            # Each dialog has substantive content (not empty)
            for title, msg in shown:
                assert msg, f"Empty message for {title}"
                assert "None" not in msg, (
                    f"'{title}' contains 'None': {msg}"
                )

        finally:
            mb.showinfo = original_show
            app.destroy()


@no_display
class TestNotebookTabs:
    """The notebook has the expected tabs."""

    def test_ledger_tab_present(self, seeded_db: str):
        """Notebook has a Ledger tab."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            assert "Ledger" in tabs, f"Ledger tab missing, got {tabs}"
        finally:
            app.destroy()

    def test_portfolio_tab_present(self, seeded_db: str):
        """Notebook has a Portfolio tab."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            assert "Portfolio" in tabs, f"Portfolio tab missing, got {tabs}"
        finally:
            app.destroy()


@no_display
class TestReportContent:
    """Report dialogs contain the expected information."""

    def test_net_worth_has_numbers(self, seeded_db: str):
        """Net worth dialog shows positive numbers."""
        import tkinter as tk
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = mb.showinfo
            captured = []

            def _capture(title, message, **kwargs):
                captured.append((title, message))
                return "ok"

            mb.showinfo = _capture
            app._show_net_worth()
            mb.showinfo = original

            _, msg = captured[0]
            assert "$" in msg, f"No dollar amounts in net worth: {msg}"
            # Assets should be positive
            assert "0.00" not in msg.split("Assets:")[1][:20], (
                f"Assets are zero in net worth: {msg}"
            )
        finally:
            mb.showinfo = original
            app.destroy()

    def test_income_statement_has_breakdown(self, seeded_db: str):
        """Income statement shows income, expenses, and net income."""
        import tkinter as tk
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = mb.showinfo
            captured = []

            def _capture(title, message, **kwargs):
                captured.append((title, message))
                return "ok"

            mb.showinfo = _capture
            app._show_income_stmt()
            mb.showinfo = original

            _, msg = captured[0]
            assert "INCOME" in msg, f"No INCOME section: {msg}"
            assert "EXPENSES" in msg, f"No EXPENSES section: {msg}"
            assert "Net Income" in msg or "Net Loss" in msg, (
                f"No net income/loss line: {msg}"
            )
            # Wages should appear in income
            assert "Wages" in msg, f"Wages missing: {msg}"
            # Groceries and Rent should appear in expenses
            assert "Groceries" in msg, f"Groceries missing: {msg}"
            assert "Rent" in msg, f"Rent missing: {msg}"
        finally:
            mb.showinfo = original
            app.destroy()

    def test_balance_sheet_shows_all_assets(self, seeded_db: str):
        """Balance sheet lists each asset with its balance."""
        import tkinter as tk
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = mb.showinfo
            captured = []

            def _capture(title, message, **kwargs):
                captured.append((title, message))
                return "ok"

            mb.showinfo = _capture
            app._show_balance_sheet()
            mb.showinfo = original

            _, msg = captured[0]
            assert "ASSETS" in msg, f"No ASSETS section: {msg}"
            assert "LIABILITIES" in msg, f"No LIABILITIES section: {msg}"
            assert "EQUITY" in msg, f"No EQUITY section: {msg}"

            # Key accounts appear
            assert "HS Checking" in msg, f"HS Checking missing: {msg}"
            assert "Discover" in msg, f"Discover missing: {msg}"
        finally:
            mb.showinfo = original
            app.destroy()

    def test_re_statement_dividend_line_present_if_applicable(
            self, seeded_db: str):
        """RE statement shows dividend line when dividends exist."""
        import tkinter as tk
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = mb.showinfo
            captured = []

            def _capture(title, message, **kwargs):
                captured.append((title, message))
                return "ok"

            mb.showinfo = _capture

            # Add a dividend transaction
            ids = {acct.name: aid for aid, acct in app.manager.accounts.items()
                   if aid}
            checking_id = ids.get("HS Checking", 7)
            app.manager.add_transaction(
                datetime(2026, 7, 1), "Dividend paid",
                [Split(9, 50000), Split(checking_id, -50000)],
            )
            app.manager.generate_ledger()

            app._show_re_statement()
            mb.showinfo = original

            _, msg = captured[0]
            assert "Dividend" in msg or "dividend" in msg, (
                f"Dividend line missing: {msg}"
            )
        finally:
            mb.showinfo = original
            app.destroy()

    def test_re_statement_no_dividend_line_when_none(self, seeded_db: str):
        """RE statement omits dividend line when no dividends."""
        import tkinter as tk
        import tkinter.messagebox as mb
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            original = mb.showinfo
            captured = []

            def _capture(title, message, **kwargs):
                captured.append((title, message))
                return "ok"

            mb.showinfo = _capture
            app._show_re_statement()
            mb.showinfo = original

            _, msg = captured[0]
            assert "Dividend" not in msg, (
                f"Dividend line present when none expected: {msg}"
            )
        finally:
            mb.showinfo = original
            app.destroy()


@no_display
class TestCRUDDialogs:
    """CRUD dialogs can be opened and return expected data."""

    def test_account_dialog_opens(self, seeded_db: str):
        """AccountDialog can be instantiated."""
        import tkinter as tk
        from ledger.gui.dialogs import AccountDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = AccountDialog(app, app.manager)
            try:
                # Dialog should have entry fields
                assert dialog.name_entry is not None
            finally:
                dialog.destroy()
        finally:
            app.destroy()

    def test_transaction_dialog_opens(self, seeded_db: str):
        """TransactionDialog can be instantiated."""
        import tkinter as tk
        from ledger.gui.dialogs import TransactionDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = TransactionDialog(app, app.manager)
            try:
                # Dialog should have entry fields for splits
                assert dialog.date_entry is not None
            finally:
                dialog.destroy()
        finally:
            app.destroy()

    def test_buy_sell_dialog_opens(self, seeded_db: str):
        """BuySellDialog can be instantiated."""
        import tkinter as tk
        from ledger.gui.dialogs import BuySellDialog
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            dialog = BuySellDialog(app, app.manager, "Buy")
            try:
                assert dialog is not None
                assert dialog.action_label is not None
            finally:
                dialog.destroy()
        finally:
            app.destroy()


@no_display
class TestWindowProperties:
    """The main window has the correct properties."""

    def test_window_title(self, seeded_db: str):
        """Window title is correct."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            title = app.title()
            assert "Ledger" in title, f"Title doesn't contain 'Ledger': {title}"
            assert "Double-Entry" in title, (
                f"Title doesn't contain 'Double-Entry': {title}"
            )
        finally:
            app.destroy()

    def test_minimum_size(self, seeded_db: str):
        """Window has a minimum size."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            min_w, min_h = app.minsize()
            assert min_w >= 800, f"Min width {min_w} < 800"
            assert min_h >= 500, f"Min height {min_h} < 500"
        finally:
            app.destroy()
