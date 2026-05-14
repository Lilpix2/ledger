"""Component tests: Close Month feature — File → Close Month… menu action.

Tests
-----
- Menu item exists in the File menu
- Clicking it shows a confirmation dialog
- Confirm triggers close_temps + generate_ledger + UI refresh
- Cancel does nothing
- Status bar reflects closed state
- Income/expense accounts zeroed after close

Boundary
--------
- Backend mocked via ``fast_seeded`` (MockDB)
- Menu actions triggered via ``actions()`` traversal
- ``QMessageBox.question`` patched to avoid blocking
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow,
                                     QMessageBox, QStatusBar, QTreeView,
                                     QTableView)
    from PySide6.QtGui import QAction
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.gui_pyside.gui_app_pyside import LedgerGUI


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _find_menu_action(menu_text: str, action_text: str, window: LedgerGUI) -> QAction | None:
    """Find a QAction by menu name and action text."""
    menubar = window.menuBar()
    for menu in menubar.findChildren(type(menubar.addMenu("_"))):
        pass  # We'll traverse actions instead
    for action in menubar.actions():
        if action.text() == menu_text:
            menu = action.menu()
            if menu:
                for sub_action in menu.actions():
                    if sub_action.text() == action_text:
                        return sub_action
    return None


def _trigger_action(window: LedgerGUI, menu_label: str, action_label: str) -> None:
    """Find and trigger a menu action, keeping C++ ref alive."""
    menubar = window.menuBar()
    for menu_action in menubar.actions():
        menu = menu_action.menu()
        if menu and menu_action.text() == menu_label:
            for action in menu.actions():
                if action.text() == action_label:
                    action.trigger()
                    return
    pytest.fail(f"Action '{action_label}' not found under menu '{menu_label}'")


def _get_action_texts(window: LedgerGUI, menu_label: str) -> list[str]:
    """Return non-separator action text under a menu."""
    texts: list[str] = []
    menubar = window.menuBar()
    for menu_action in menubar.actions():
        menu = menu_action.menu()
        if menu and menu_action.text() == menu_label:
            for action in menu.actions():
                if not action.isSeparator():
                    texts.append(action.text())
    return texts


# ═══════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════


class TestCloseMonthMenu:
    """Close Month menu item existence and structure."""

    def test_menu_item_exists(self, qt_app, fast_seeded):
        """Close Month… action exists under the File menu."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            texts = _get_action_texts(window, "File")
            assert "Close Month…" in texts
        finally:
            window.close()

    def test_menu_item_location_before_quit(self, qt_app, fast_seeded):
        """Close Month appears before Quit."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            texts = _get_action_texts(window, "File")
            assert "Close Month…" in texts
            assert "Quit" in texts
            assert texts.index("Close Month…") < texts.index("Quit")
        finally:
            window.close()


class TestCloseMonthConfirm:
    """Close Month confirmation dialog behavior."""

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_confirm_calls_close_temps(self, mock_q, qt_app, fast_seeded):
        """Clicking Yes triggers close_temps and generate_ledger."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager

            # Record pre-close state
            wages = next(aid for aid, a in m.accounts.items()
                        if a.name == "Wages")
            assert m.get_display_balance(wages) != 0  # income exists

            # Trigger the action
            _trigger_action(window, "File", "Close Month…")
            QApplication.processEvents()

            # Income accounts zeroed
            assert m.get_display_balance(wages) == 0
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_confirm_refreshes_status_bar(self, mock_q, qt_app, fast_seeded):
        """After close, status bar shows balanced message."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            _trigger_action(window, "File", "Close Month…")
            QApplication.processEvents()

            status = window.statusBar()
            msg = status.currentMessage()
            assert "✓" in msg or "Balanced" in msg or "closed" in msg.lower()
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.No)
    def test_cancel_does_not_close(self, mock_q, qt_app, fast_seeded):
        """Clicking No leaves income accounts untouched."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager

            wages = next(aid for aid, a in m.accounts.items()
                        if a.name == "Wages")
            bal_before = m.get_display_balance(wages)

            _trigger_action(window, "File", "Close Month…")
            QApplication.processEvents()

            # Balances unchanged
            assert m.get_display_balance(wages) == bal_before
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_confirm_equation_stays_balanced(self, mock_q, qt_app, fast_seeded):
        """Accounting equation holds after close."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            _trigger_action(window, "File", "Close Month…")
            QApplication.processEvents()

            eq = window._manager.check_accounting_equation()
            assert eq["balanced"]
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_confirm_all_temps_zeroed(self, mock_q, qt_app, fast_seeded):
        """All income and expense accounts reset to zero."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager

            # Find income and expense accounts
            income_ids = [aid for aid, a in m.accounts.items()
                         if a.acct_type == "INCOME"]
            expense_ids = [aid for aid, a in m.accounts.items()
                          if a.acct_type == "EXPENSE"]

            _trigger_action(window, "File", "Close Month…")
            QApplication.processEvents()

            for aid in income_ids:
                assert m.get_display_balance(aid) == 0, (
                    f"Income account {m.accounts[aid].name} not zeroed"
                )
            for aid in expense_ids:
                assert m.get_display_balance(aid) == 0, (
                    f"Expense account {m.accounts[aid].name} not zeroed"
                )
        finally:
            window.close()

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_confirm_closing_entries_in_table(self, mock_q, qt_app, fast_seeded):
        """Closing entries appear in the transaction table model."""
        window = LedgerGUI(fast_seeded)
        window.show()

        try:
            m = window._manager
            txn_before = len(m.journal.transactions)

            _trigger_action(window, "File", "Close Month…")
            QApplication.processEvents()

            # Additional closing entries were created
            assert len(m.journal.transactions) > txn_before
        finally:
            window.close()
        QApplication.processEvents()
