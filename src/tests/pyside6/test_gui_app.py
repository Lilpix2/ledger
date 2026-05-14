"""Component tests: PySide6 main window — ``gui_app_pyside.py``.

Tests LedgerGUI main window structure, menu bar, tabs, toolbar,
status bar, account tree, transaction table, portfolio tab,
and refresh/trigger dispatch.

Boundary
--------
- Backend mocked via ``fast_manager`` / ``fast_seeded`` (MockDB)
- Dialog triggers are mocked to avoid modal ``exec()``
- ``QMessageBox.question`` patched in close-month tests
- Qt offscreen mode for headless environments
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QTabWidget, QStatusBar,
        QTreeView, QTableView, QPushButton, QLabel, QMenuBar,
        QWidget, QMessageBox, QDialog,
    )
    from PySide6.QtGui import QAction
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.gui_pyside.gui_app_pyside import LedgerGUI, LedgerTableModel, PortfolioTableModel

from .conftest import find_widget, click_button


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _get_menu_action_texts(window: LedgerGUI, menu_label: str) -> list[str]:
    """Return non-separator action texts under a menu."""
    texts: list[str] = []
    menubar = window.menuBar()
    for menu_action in menubar.actions():
        if menu_action.text() == menu_label:
            menu = menu_action.menu()
            if menu:
                for action in menu.actions():
                    if not action.isSeparator():
                        texts.append(action.text())
    return texts


def _get_all_menu_labels(window: LedgerGUI) -> list[str]:
    """Return all top-level menu labels."""
    menubar = window.menuBar()
    return [a.text() for a in menubar.actions() if not a.isSeparator()]


# ═══════════════════════════════════════════════════════════════════
#  Window Structure
# ═══════════════════════════════════════════════════════════════════


class TestLedgerGUIWindow:
    """Window construction and basic structure."""

    def test_construct_with_manager(self, qt_app, fast_seeded):
        """Constructs successfully with an AccountManager object."""
        window = LedgerGUI(fast_seeded)
        assert window is not None
        assert isinstance(window, QMainWindow)
        window.close()

    def test_window_title(self, qt_app, fast_seeded):
        """Window title is 'Ledger — Double-Entry Accounting'."""
        window = LedgerGUI(fast_seeded)
        assert window.windowTitle() == "Ledger — Double-Entry Accounting"
        window.close()

    def test_window_default_size(self, qt_app, fast_seeded):
        """Window initial size is 1200×700."""
        window = LedgerGUI(fast_seeded)
        assert window.width() == 1200
        assert window.height() == 700
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Menu Structure
# ═══════════════════════════════════════════════════════════════════


class TestMenuStructure:
    """Menu bar presence and action layout."""

    def test_menu_bar_exists(self, qt_app, fast_seeded):
        """A menu bar is present."""
        window = LedgerGUI(fast_seeded)
        assert window.menuBar() is not None
        window.close()

    def test_all_top_level_menus(self, qt_app, fast_seeded):
        """Top-level menus: File, Accounts, Transactions, Help."""
        window = LedgerGUI(fast_seeded)
        labels = _get_all_menu_labels(window)
        assert "File" in labels, f"Missing 'File': {labels}"
        assert "Accounts" in labels
        assert "Transactions" in labels
        assert "Help" in labels
        window.close()

    def test_file_menu_actions(self, qt_app, fast_seeded):
        """File menu: Refresh, Close Month…, separator, Quit."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "File")
        assert "Refresh" in texts
        assert "Close Month…" in texts
        assert "Quit" in texts
        assert texts.index("Close Month…") < texts.index("Quit")
        window.close()

    def test_accounts_menu_has_new(self, qt_app, fast_seeded):
        """Accounts menu: New Account…"""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Accounts")
        assert "New Account…" in texts
        window.close()

    def test_transactions_menu_actions(self, qt_app, fast_seeded):
        """Transactions menu: New Transaction…, separator, Income Statement,
        Balance Sheet, Net Worth."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Transactions")
        assert "New Transaction…" in texts
        assert "Income Statement" in texts
        assert "Balance Sheet" in texts
        assert "Net Worth" in texts
        # New Transaction comes first
        assert texts.index("New Transaction…") < texts.index("Income Statement")
        window.close()

    def test_help_menu_has_about(self, qt_app, fast_seeded):
        """Help menu: About."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Help")
        assert "About" in texts
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Tab Structure
# ═══════════════════════════════════════════════════════════════════


class TestTabStructure:
    """Tab widget existence and labels."""

    def test_tab_widget_exists(self, qt_app, fast_seeded):
        """Main tab widget has objectName 'mainTabs'."""
        window = LedgerGUI(fast_seeded)
        tabs = window.findChild(QTabWidget, "mainTabs")
        assert tabs is not None
        window.close()

    def test_tabs_include_ledger(self, qt_app, fast_seeded):
        """First tab is 'Ledger'."""
        window = LedgerGUI(fast_seeded)
        tabs = window.findChild(QTabWidget, "mainTabs")
        assert tabs is not None
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        assert "Ledger" in labels
        assert labels[0] == "Ledger"
        window.close()

    def test_tabs_include_portfolio(self, qt_app, fast_seeded):
        """Portfolio tab exists."""
        window = LedgerGUI(fast_seeded)
        tabs = window.findChild(QTabWidget, "mainTabs")
        assert tabs is not None
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        assert "Portfolio" in labels
        window.close()

    def test_tab_switching_by_index(self, qt_app, fast_seeded):
        """Switching tabs via setCurrentIndex changes visible widget."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        tabs = window.findChild(QTabWidget, "mainTabs")
        assert tabs is not None

        # Start at Ledger (index 0)
        assert tabs.currentIndex() == 0

        # Switch to Portfolio (index 1)
        tabs.setCurrentIndex(1)
        QApplication.processEvents()
        assert tabs.currentIndex() == 1

        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Toolbar
# ═══════════════════════════════════════════════════════════════════


class TestToolbar:
    """Ledger tab toolbar buttons."""

    def test_toolbar_has_new_account_button(self, qt_app, fast_seeded):
        """Toolbar contains 'New Account' button."""
        window = LedgerGUI(fast_seeded)
        btn = window.findChild(QPushButton, "NewAccount")
        assert btn is not None
        assert btn.text() == "New Account"
        window.close()

    def test_toolbar_has_new_transaction_button(self, qt_app, fast_seeded):
        """Toolbar contains 'New Transaction' button."""
        window = LedgerGUI(fast_seeded)
        btn = window.findChild(QPushButton, "NewTransaction")
        assert btn is not None
        assert btn.text() == "New Transaction"
        window.close()

    def test_toolbar_has_refresh_button(self, qt_app, fast_seeded):
        """Toolbar contains 'Refresh' button."""
        window = LedgerGUI(fast_seeded)
        btn = window.findChild(QPushButton, "Refresh")
        assert btn is not None
        assert btn.text() == "Refresh"
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Status Bar
# ═══════════════════════════════════════════════════════════════════


class TestStatusBar:
    """Status bar initial state and refresh behavior."""

    def test_status_bar_exists(self, qt_app, fast_seeded):
        """A QStatusBar is configured."""
        window = LedgerGUI(fast_seeded)
        status = window.statusBar()
        assert status is not None
        window.close()

    def test_status_bar_initial_message_not_empty(self, qt_app, fast_seeded):
        """Status bar has a non-empty initial message."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        status = window.statusBar()
        msg = status.currentMessage()
        assert msg != "", "Status bar message should not be empty"
        window.close()

    def test_status_includes_assets(self, qt_app, fast_seeded):
        """Status message contains formatted asset value."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        msg = window.statusBar().currentMessage()
        assert "Assets:" in msg
        assert "$" in msg
        window.close()

    def test_status_includes_liabilities(self, qt_app, fast_seeded):
        """Status message contains formatted liability value."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        msg = window.statusBar().currentMessage()
        assert "Liabilities:" in msg
        window.close()

    def test_status_includes_net_worth(self, qt_app, fast_seeded):
        """Status message contains net worth."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        msg = window.statusBar().currentMessage()
        assert "Net Worth:" in msg
        window.close()

    def test_status_shows_balanced_checkmark(self, qt_app, fast_seeded):
        """Balanced data shows ✓ in status bar."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        msg = window.statusBar().currentMessage()
        assert "✓" in msg, f"Expected checkmark in: '{msg}'"
        window.close()

    def test_status_updates_after_transaction(self, qt_app, fast_seeded):
        """Adding a transaction and refreshing updates the status bar."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        groceries = next(aid for aid, a in fast_seeded.accounts.items()
                         if a.name == "Groceries")

        fast_seeded.add_transaction(
            datetime(2026, 7, 1), "More food",
            [Split(groceries, 2500), Split(checking, -2500)],
        )
        fast_seeded.generate_ledger()
        window._refresh_all_internal()
        QApplication.processEvents()

        msg = window.statusBar().currentMessage()
        assert "$" in msg
        assert "✓" in msg
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Account Tree
# ═══════════════════════════════════════════════════════════════════


class TestAccountTree:
    """Account tree view presence and model population."""

    def test_tree_view_exists(self, qt_app, fast_seeded):
        """Account tree QTreeView exists with objectName 'accountTree'."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        assert tree is not None
        window.close()

    def test_tree_model_populated(self, qt_app, fast_seeded):
        """Tree model has root items matching top-level parent accounts."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        model = tree.model()
        assert model is not None
        # Should have at least: Assets, Liabilities, Equity, Income, Expenses
        assert model.rowCount() >= 5, (
            f"Expected ≥5 root items, got {model.rowCount()}"
        )
        window.close()

    def test_tree_root_labels_contain_types(self, qt_app, fast_seeded):
        """Root items show account name and type."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        model = tree.model()

        labels = []
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            labels.append(model.data(idx))

        # The parent accounts should include type indicators
        has_asset_label = any("ASSET" in l for l in labels)
        assert has_asset_label, f"No ASSET label in: {labels}"
        window.close()

    def test_tree_shows_balances(self, qt_app, fast_seeded):
        """Each tree row has a balance in column 1."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        model = tree.model()

        found_balance = False
        for row in range(model.rowCount()):
            bal_idx = model.index(row, 1)
            bal_text = model.data(bal_idx)
            if bal_text and "$" in str(bal_text):
                found_balance = True
                break

        assert found_balance, "No balance values found in tree column 1"
        window.close()

    def test_tree_header_labels(self, qt_app, fast_seeded):
        """Tree model header has 'Account' and 'Balance'."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        model = tree.model()

        h0 = model.headerData(0, Qt.Orientation.Horizontal)
        h1 = model.headerData(1, Qt.Orientation.Horizontal)
        assert h0 is not None
        assert h1 is not None
        assert "Account" in str(h0)
        assert "Balance" in str(h1)
        window.close()

    def test_tree_rebuilds_after_refresh(self, qt_app, fast_seeded):
        """_refresh_all_internal rebuilds the tree model from scratch."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        model_before = tree.model()

        fast_seeded.add_account("NewParent", 1)
        fast_seeded.generate_ledger()
        window._refresh_all_internal()

        model_after = tree.model()
        # AccountTreeModel is always rebuilt (new object), so references differ
        assert model_after.rowCount() >= model_before.rowCount()
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Transaction Table
# ═══════════════════════════════════════════════════════════════════


class TestTransactionTable:
    """Transaction table view and model."""

    def test_table_view_exists(self, qt_app, fast_seeded):
        """Transaction QTableView exists with objectName 'transactionTable'."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        assert table is not None
        window.close()

    def test_table_model_populated(self, qt_app, fast_seeded):
        """Table model has rows for seeded transactions."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        model = table.model()
        assert model is not None
        assert model.rowCount() >= 3, (
            f"Expected ≥3 transactions, got {model.rowCount()}"
        )
        window.close()

    def test_table_columns_are_date_description_amount(self, qt_app, fast_seeded):
        """Table headers: Date, Description, Amount."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        model = table.model()

        headers = [
            model.headerData(i, Qt.Orientation.Horizontal)
            for i in range(model.columnCount())
        ]
        header_strs = [str(h) for h in headers]
        assert "Date" in header_strs
        assert "Description" in header_strs
        assert "Amount" in header_strs
        assert len(header_strs) == 3
        window.close()

    def test_column_0_contains_dates(self, qt_app, fast_seeded):
        """First column contains date strings."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        model = table.model()

        val = model.data(model.index(0, 0))
        assert val is not None
        assert len(str(val)) >= 8  # at least MM-DD-YY or YYYY-MM-DD
        window.close()

    def test_column_2_contains_amounts(self, qt_app, fast_seeded):
        """Third column contains formatted currency strings."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        model = table.model()

        val = model.data(model.index(0, 2))
        assert val is not None
        assert isinstance(val, str)
        assert "$" in str(val)
        window.close()

    def test_table_reflects_new_transaction(self, qt_app, fast_seeded):
        """Adding a transaction and refreshing increases row count."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        model = table.model()
        before = model.rowCount()

        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        groceries = next(aid for aid, a in fast_seeded.accounts.items()
                         if a.name == "Groceries")
        fast_seeded.add_transaction(
            datetime(2026, 7, 5), "Test txn",
            [Split(groceries, 3000), Split(checking, -3000)],
        )
        fast_seeded.generate_ledger()
        window._table_model.refresh()

        assert model.rowCount() == before + 1
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Portfolio Tab
# ═══════════════════════════════════════════════════════════════════


class TestPortfolioTab:
    """Portfolio tab table and summary label."""

    def _switch_to_portfolio(self, window):
        """Helper to switch to Portfolio tab."""
        tabs = window.findChild(QTabWidget, "mainTabs")
        assert tabs is not None
        tabs.setCurrentIndex(1)
        QApplication.processEvents()

    def test_portfolio_table_exists(self, qt_app, fast_seeded):
        """Portfolio tab has a table with objectName 'portfolioTable'."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        self._switch_to_portfolio(window)
        table = window.findChild(QTableView, "portfolioTable")
        assert table is not None
        window.close()

    def test_portfolio_summary_label_exists(self, qt_app, fast_seeded):
        """Portfolio tab has a bold summary label."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        self._switch_to_portfolio(window)
        tabs = window.findChild(QTabWidget, "mainTabs")
        tab_widget = tabs.widget(1)
        labels = tab_widget.findChildren(QLabel)
        # Find the bold summary label
        bold_labels = [
            l for l in labels
            if "bold" in (l.styleSheet() or "") or "Market Value" in l.text()
        ]
        assert any(bold_labels), "No bold summary label found in Portfolio tab"
        window.close()

    def test_portfolio_summary_shows_market_value(self, qt_app, fast_seeded):
        """Summary label contains 'Total Market Value' after refresh."""
        brokerage = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.account_subtype == "brokerage")
        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        fast_seeded.buy_security(
            datetime(2026, 2, 1), "Buy VTI",
            brokerage, checking, "VTI", 10, 27500,
        )
        fast_seeded.save_price("VTI", "latest", 29000)
        fast_seeded.generate_ledger()

        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        # Ensure portfolio is refreshed
        window._refresh_portfolio()
        self._switch_to_portfolio(window)

        tabs = window.findChild(QTabWidget, "mainTabs")
        tab_widget = tabs.widget(1)
        labels = tab_widget.findChildren(QLabel)
        summary = next((l for l in labels if "Market Value" in l.text()), None)
        assert summary is not None
        assert "$" in summary.text()
        window.close()

    def test_portfolio_table_populated_with_holdings(self, qt_app, fast_seeded):
        """Portfolio table has rows for brokerage holdings with prices."""
        # Add holdings to the seeded data
        brokerage = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.account_subtype == "brokerage")
        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        fast_seeded.buy_security(
            datetime(2026, 2, 1), "Buy VTI",
            brokerage, checking, "VTI", 10, 27500,
        )
        fast_seeded.save_price("VTI", "latest", 29000)
        fast_seeded.generate_ledger()

        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        self._switch_to_portfolio(window)
        table = window.findChild(QTableView, "portfolioTable")
        model = table.model()
        assert model is not None
        assert model.rowCount() >= 1
        window.close()

    def test_portfolio_headers(self, qt_app, fast_seeded):
        """Portfolio table has correct column headers."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        self._switch_to_portfolio(window)
        table = window.findChild(QTableView, "portfolioTable")
        model = table.model()
        expected = ["Account", "Ticker", "Shares", "Cost", "Price",
                     "Market Val", "P&L", "P&L %"]
        headers = [
            str(model.headerData(i, Qt.Orientation.Horizontal))
            for i in range(model.columnCount())
        ]
        assert headers == expected, f"Headers mismatch: {headers}"
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Refresh
# ═══════════════════════════════════════════════════════════════════


class TestRefresh:
    """Refresh action rebuilds all UI components."""

    def test_refresh_all_rebuilds_tree_model(self, qt_app, fast_seeded):
        """_refresh_all_internal replaces the tree view model."""
        window = LedgerGUI(fast_seeded)
        tree = window.findChild(QTreeView, "accountTree")
        old_model = tree.model()

        # Add data that changes the tree
        fast_seeded.add_account("FreshAsset", 1)
        fast_seeded.generate_ledger()
        window._refresh_all_internal()

        new_model = tree.model()
        assert new_model.rowCount() >= old_model.rowCount()
        window.close()

    def test_refresh_all_rebuilds_table(self, qt_app, fast_seeded):
        """_refresh_all_internal refreshes the transaction table model."""
        window = LedgerGUI(fast_seeded)
        table = window.findChild(QTableView, "transactionTable")
        model = table.model()
        before = model.rowCount()

        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        groceries = next(aid for aid, a in fast_seeded.accounts.items()
                         if a.name == "Groceries")
        fast_seeded.add_transaction(
            datetime(2026, 7, 10), "After refresh",
            [Split(groceries, 2000), Split(checking, -2000)],
        )
        fast_seeded.generate_ledger()
        window._refresh_all_internal()

        assert model.rowCount() == before + 1
        window.close()

    def test_refresh_all_updates_status(self, qt_app, fast_seeded):
        """_refresh_all_internal calls _refresh_status."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        # Track that _refresh_status is called as part of _refresh_all_internal
        original_status = window._refresh_status
        called = [False]

        def track():
            called[0] = True
            original_status()

        window._refresh_status = track
        window._refresh_all_internal()

        assert called[0]
        window.close()

    def test_refresh_all_updates_portfolio(self, qt_app, fast_seeded):
        """_refresh_all_internal calls _refresh_portfolio."""
        window = LedgerGUI(fast_seeded)
        original = window._refresh_portfolio
        called = [False]

        def track():
            called[0] = True
            original()

        window._refresh_portfolio = track
        window._refresh_all_internal()

        assert called[0]
        window.close()

    def test_refresh_menu_triggers_refresh(self, qt_app, fast_seeded):
        """File → Refresh calls _on_toolbar('Refresh')."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        with patch.object(window, '_on_toolbar') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "File":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "Refresh":
                                action.trigger()
                                break
                    break

        mock.assert_called_once_with("Refresh")
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Dialog Triggers
# ═══════════════════════════════════════════════════════════════════


class TestDialogTriggers:
    """Toolbar buttons and menu items trigger the correct dialogs."""

    def test_new_account_button_triggers_dialog(self, qt_app, fast_seeded):
        """Clicking 'New Account' toolbar button calls _dialog_new_account."""
        window = LedgerGUI(fast_seeded)

        with patch.object(window, '_dialog_new_account') as mock:
            btn = window.findChild(QPushButton, "NewAccount")
            assert btn is not None
            btn.click()

        mock.assert_called_once()
        window.close()

    def test_new_transaction_button_triggers_dialog(self, qt_app, fast_seeded):
        """Clicking 'New Transaction' toolbar button calls _dialog_new_transaction."""
        window = LedgerGUI(fast_seeded)

        with patch.object(window, '_dialog_new_transaction') as mock:
            btn = window.findChild(QPushButton, "NewTransaction")
            assert btn is not None
            btn.click()

        mock.assert_called_once()
        window.close()

    def test_refresh_button_triggers_on_toolbar(self, qt_app, fast_seeded):
        """Clicking 'Refresh' toolbar button calls _on_toolbar('Refresh')."""
        window = LedgerGUI(fast_seeded)

        with patch.object(window, '_on_toolbar') as mock:
            btn = window.findChild(QPushButton, "Refresh")
            assert btn is not None
            btn.click()

        mock.assert_called_once_with("Refresh")
        window.close()

    def test_menu_new_account_triggers_on_toolbar(self, qt_app, fast_seeded):
        """Accounts → New Account… calls _on_toolbar('New Account')."""
        window = LedgerGUI(fast_seeded)

        with patch.object(window, '_on_toolbar') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "Accounts":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "New Account…":
                                action.trigger()
                                break
                    break

        mock.assert_called_once_with("New Account")
        window.close()

    def test_menu_new_transaction_triggers_on_toolbar(self, qt_app, fast_seeded):
        """Transactions → New Transaction… calls _on_toolbar('New Transaction')."""
        window = LedgerGUI(fast_seeded)

        with patch.object(window, '_on_toolbar') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "Transactions":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "New Transaction…":
                                action.trigger()
                                break
                    break

        mock.assert_called_once_with("New Transaction")
        window.close()


# ═══════════════════════════════════════════════════════════════════
#  _on_toolbar Dispatch
# ═══════════════════════════════════════════════════════════════════


class TestOnToolbarDispatch:
    """_on_toolbar routes actions to the right methods."""

    def test_new_account_dispatches_to_dialog(self, qt_app, fast_seeded):
        """_on_toolbar('New Account') calls _dialog_new_account."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_dialog_new_account') as mock:
            window._on_toolbar("New Account")
        mock.assert_called_once()
        window.close()

    def test_new_transaction_dispatches_to_dialog(self, qt_app, fast_seeded):
        """_on_toolbar('New Transaction') calls _dialog_new_transaction."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_dialog_new_transaction') as mock:
            window._on_toolbar("New Transaction")
        mock.assert_called_once()
        window.close()

    def test_refresh_dispatches_to_refresh(self, qt_app, fast_seeded):
        """_on_toolbar('Refresh') calls _refresh_all_internal."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_refresh_all_internal') as mock:
            window._on_toolbar("Refresh")
        mock.assert_called_once()
        window.close()

    def test_on_dialog_success_calls_refresh(self, qt_app, fast_seeded):
        """_on_dialog_success calls _refresh_all_internal."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_refresh_all_internal') as mock:
            window._on_dialog_success()
        mock.assert_called_once()
        window.close()

    def test_dialog_new_account_creates_dialog(self, qt_app, fast_seeded, mock_success):
        """_dialog_new_account creates an AccountDialog (patched to avoid exec)."""
        from ledger.gui_pyside.dialogs import AccountDialog
        window = LedgerGUI(fast_seeded)

        with patch.object(AccountDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
            window._dialog_new_account()
            mock_exec.assert_called_once()

        window.close()

    def test_dialog_new_transaction_creates_dialog(self, qt_app, fast_seeded, mock_success):
        """_dialog_new_transaction creates a TransactionDialog (patched to avoid exec)."""
        from ledger.gui_pyside.dialogs import TransactionDialog
        window = LedgerGUI(fast_seeded)

        with patch.object(TransactionDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
            window._dialog_new_transaction()
            mock_exec.assert_called_once()

        window.close()


# ═══════════════════════════════════════════════════════════════════
#  Close Month (through main window dispatch)
# ═══════════════════════════════════════════════════════════════════


class TestCloseMonthDispatch:
    """Close Month trigger and status update (non-modal path)."""

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_close_month_via_file_menu(self, mock_q, qt_app, fast_seeded):
        """File → Close Month… → Yes zeroes income accounts."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        wages = next(aid for aid, a in fast_seeded.accounts.items()
                     if a.name == "Wages")
        assert fast_seeded.get_display_balance(wages) != 0

        try:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "File":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "Close Month…":
                                action.trigger()
                                break
                    break

            QApplication.processEvents()
            assert fast_seeded.get_display_balance(wages) == 0
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_close_month_updates_status_balanced(self, mock_q, qt_app, fast_seeded):
        """Close Month → Yes updates status bar with balanced message."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "File":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "Close Month…":
                                action.trigger()
                                break
                    break

            QApplication.processEvents()
            msg = window.statusBar().currentMessage()
            assert "✓" in msg or "closed" in msg.lower()
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.No)
    def test_close_month_cancelled_does_nothing(self, mock_q, qt_app, fast_seeded):
        """File → Close Month… → No leaves income unchanged."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        wages = next(aid for aid, a in fast_seeded.accounts.items()
                     if a.name == "Wages")
        bal_before = fast_seeded.get_display_balance(wages)

        try:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "File":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "Close Month…":
                                action.trigger()
                                break
                    break

            QApplication.processEvents()
            assert fast_seeded.get_display_balance(wages) == bal_before
        finally:
            window.close()


# ═══════════════════════════════════════════════════════════════════
#  LedgerTableModel
# ═══════════════════════════════════════════════════════════════════


class TestLedgerTableModel:
    """LedgerTableModel unit behavior (pure model, needs qt_app for QModelIndex)."""

    def test_columns_are_three(self, qt_app, fast_seeded):
        """Model has exactly 3 columns."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        assert model.columnCount() == 3

    def test_row_count_matches_transactions(self, qt_app, fast_seeded):
        """Model row count equals number of transactions."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        n_txns = len(fast_seeded.journal.transactions)
        assert model.rowCount() == n_txns

    def test_data_col0_is_date_string(self, qt_app, fast_seeded):
        """Column 0 returns formatted date strings."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        if model.rowCount() > 0:
            val = model.data(model.index(0, 0))
            assert val is not None
            assert len(str(val)) >= 8

    def test_data_col2_is_amount_string(self, qt_app, fast_seeded):
        """Column 2 returns dollar-formatted amount."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        if model.rowCount() > 0:
            val = model.data(model.index(0, 2))
            assert val is not None
            assert isinstance(val, str)
            assert "$" in str(val)

    def test_empty_model_no_crash(self, qt_app, fast_manager):
        """Empty manager produces empty model with no errors."""
        model = LedgerTableModel(fast_manager)
        model.refresh()
        assert model.rowCount() == 0
        # Check that data() calls don't crash
        assert model.data(model.index(0, 0)) is None
        assert model.data(model.index(-1, 0)) is None
        assert model.data(model.index(0, 2)) is None


# ═══════════════════════════════════════════════════════════════════
#  PortfolioTableModel (wraps pyside6_e2e coverage into component)
# ═══════════════════════════════════════════════════════════════════


class TestPortfolioTableModelComponent:
    """PortfolioTableModel — component-level coverage beyond existing unit tests."""

    def test_model_column_count(self, qt_app, fast_seeded):
        """Model reports 8 columns."""
        model = PortfolioTableModel(fast_seeded)
        assert model.columnCount() == 8

    def test_empty_model_column_count(self, qt_app, fast_manager):
        """Empty model still reports correct column count."""
        model = PortfolioTableModel(fast_manager)
        assert model.columnCount() == 8
        assert model.rowCount() == 0

    def test_model_has_holdings(self, qt_app, fast_seeded):
        """Model includes holdings when prices exist."""
        brokerage = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.account_subtype == "brokerage")
        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        fast_seeded.buy_security(
            datetime(2026, 2, 1), "Buy VTI",
            brokerage, checking, "VTI", 10, 27500,
        )
        fast_seeded.save_price("VTI", "latest", 29000)
        fast_seeded.generate_ledger()

        model = PortfolioTableModel(fast_seeded)
        assert model.rowCount() >= 1

    def test_data_returns_string_types(self, qt_app, fast_seeded):
        """All data cells return string values."""
        brokerage = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.account_subtype == "brokerage")
        checking = next(aid for aid, a in fast_seeded.accounts.items()
                        if a.name == "HS Checking")
        fast_seeded.buy_security(
            datetime(2026, 2, 1), "Buy VTI",
            brokerage, checking, "VTI", 10, 27500,
        )
        fast_seeded.save_price("VTI", "latest", 29000)
        fast_seeded.generate_ledger()

        model = PortfolioTableModel(fast_seeded)
        if model.rowCount() > 0:
            for col in range(model.columnCount()):
                val = model.data(model.index(0, col))
                assert isinstance(val, str), f"Col {col} returned {type(val)}: {val}"


# ═══════════════════════════════════════════════════════════════════
#  Edge Cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases for the main window."""

    def test_construct_with_db_path(self, qt_app):
        """Constructing with a string db_path works (uses AccountManager)."""
        import tempfile
        path = tempfile.mktemp(suffix=".db")
        window = LedgerGUI(db_path=path)
        assert window is not None
        assert isinstance(window._manager, AccountManager)
        window.close()

    def test_quit_menu_action_exists(self, qt_app, fast_seeded):
        """File → Quit menu action exists with 'Quit' label."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "File")
        assert "Quit" in texts
        window.close()

    def test_menu_about_triggers_report(self, qt_app, fast_seeded):
        """Help → About calls show_about."""
        import ledger.gui_pyside.reports as reports_mod
        window = LedgerGUI(fast_seeded)

        with patch.object(reports_mod, 'show_about') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "Help":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if action.text() == "About":
                                action.trigger()
                                break
                    break

        mock.assert_called_once_with(window)
        window.close()

    def test_income_stmt_menu_triggers_report(self, qt_app, fast_seeded):
        """Transactions → Income Statement calls show_income_stmt."""
        import ledger.gui_pyside.reports as reports_mod
        window = LedgerGUI(fast_seeded)

        with patch.object(reports_mod, 'show_income_stmt') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "Transactions":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if not action.isSeparator() and action.text() == "Income Statement":
                                action.trigger()
                                break
                    break

        mock.assert_called_once()
        window.close()

    def test_balance_sheet_menu_triggers_report(self, qt_app, fast_seeded):
        """Transactions → Balance Sheet calls show_balance_sheet."""
        import ledger.gui_pyside.reports as reports_mod
        window = LedgerGUI(fast_seeded)

        with patch.object(reports_mod, 'show_balance_sheet') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "Transactions":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if not action.isSeparator() and action.text() == "Balance Sheet":
                                action.trigger()
                                break
                    break

        mock.assert_called_once()
        window.close()

    def test_net_worth_menu_triggers_report(self, qt_app, fast_seeded):
        """Transactions → Net Worth calls show_net_worth."""
        import ledger.gui_pyside.reports as reports_mod
        window = LedgerGUI(fast_seeded)

        with patch.object(reports_mod, 'show_net_worth') as mock:
            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "Transactions":
                    menu = menu_action.menu()
                    if menu:
                        for action in menu.actions():
                            if not action.isSeparator() and action.text() == "Net Worth":
                                action.trigger()
                                break
                    break

        mock.assert_called_once()
        window.close()
