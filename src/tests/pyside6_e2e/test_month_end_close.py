"""E2E test: Month-end close through the PySide6 GUI menus.

Outer loop: One acceptance test that opens the app, navigates the menu
to close the month, confirms the dialog, and verifies the UI reflects
the closed state.

Tests the REAL user flow through File → Close Month… → Yes.
QMessageBox.question is patched (it's a blocking modal), but everything
else goes through the real GUI: menu navigation, backend close_temps(),
UI refresh, status bar update.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QTabWidget,
                                     QStatusBar, QTreeView, QTableView,
                                     QMessageBox)
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


def _seed_db() -> str:
    """Create a seeded temp DB with one month of activity."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)
    mgr.add_account("Rent", 5)

    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}

    mgr.add_transaction(datetime(2026, 1, 1), "Opening", [
        Split(ids["HS Checking"], 10000000),
        Split(ids["Savings"], 2000000),
        Split(ids["Discover"], -530000),
        Split(6, -11470000),
    ])
    mgr.add_transaction(datetime(2026, 6, 1), "Paycheck", [
        Split(ids["Wages"], -300000),
        Split(ids["HS Checking"], 300000),
    ])
    mgr.add_transaction(datetime(2026, 6, 2), "Rent", [
        Split(ids["Rent"], 150000),
        Split(ids["HS Checking"], -150000),
    ])
    mgr.add_transaction(datetime(2026, 6, 5), "Groceries", [
        Split(ids["Groceries"], 8500),
        Split(ids["HS Checking"], -8500),
    ])

    mgr.generate_ledger()
    del mgr
    return path


@pytest.fixture
def db_path():
    path = _seed_db()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════
#  E2E: Month-End Close via GUI
# ═══════════════════════════════════════════════════════════════════


class TestMonthEndClose:
    """One E2E acceptance test: close the month through the File menu.

    Flow:
      1. Open app → verify structure
      2. Navigate File → Close Month…
      3. Confirm the dialog (QMessageBox.question patched to return Yes)
      4. Verify status bar reflects balanced close
      5. Verify income/expense accounts zeroed
      6. Verify RE updated
      7. Verify equation balanced
    """

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_close_month_via_menu(self, mock_msgbox, qt_app, db_path):
        """Full close cycle through the GUI File → Close Month… menu."""
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI

        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager
            ids = {a.name: aid for aid, a in m.accounts.items() if aid}

            # ════════════════════════════════════════════════
            #  Phase 1: Verify structure and pre-close state
            # ════════════════════════════════════════════════

            assert window.windowTitle() == "Ledger — Double-Entry Accounting"
            status = window.statusBar()
            assert status is not None

            wages_bal = m.get_display_balance(ids["Wages"])
            re_before = m.get_display_balance(6)
            assert wages_bal == 300000, f"Wages before close: {wages_bal}"

            # ════════════════════════════════════════════════
            #  Phase 2: Navigate menu and confirm
            # ════════════════════════════════════════════════

            menubar = window.menuBar()
            for menu_action in menubar.actions():
                if menu_action.text() == "File":
                    file_menu = menu_action.menu()
                    if file_menu:
                        for action in file_menu.actions():
                            if action.text() == "Close Month…":
                                action.trigger()
                                break
                    break

            QApplication.processEvents()

            # ════════════════════════════════════════════════
            #  Phase 3: Verify post-close state
            # ════════════════════════════════════════════════

            # Income zeroed
            assert m.get_display_balance(ids["Wages"]) == 0, "Wages not zeroed"

            # Expenses zeroed
            assert m.get_display_balance(ids["Groceries"]) == 0
            assert m.get_display_balance(ids["Rent"]) == 0

            # RE increased by net income
            net_income = 300000 - 150000 - 8500  # = 141500
            re_after = m.get_display_balance(6)
            assert re_after == re_before + net_income, (
                f"RE: {re_after}, expected {re_before + net_income}"
            )

            # Equation balanced
            eq = m.check_accounting_equation()
            assert eq["balanced"]

            # Status bar shows success
            msg = status.currentMessage()
            assert "✓" in msg or "closed" in msg.lower(), (
                f"Status msg: '{msg}'"
            )

        finally:
            window.close()
