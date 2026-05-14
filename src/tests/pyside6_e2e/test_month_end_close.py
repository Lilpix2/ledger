"""E2E test: Month-end close cycle through the PySide6 GUI.

Outer loop: One acceptance test describing the full monthly closing process.

Flow:
  Open app → Verify structure → Add income/expense → Generate ledger →
  Verify pre-close balances → Run close_temps() →
  Verify temps zeroed → Verify RE updated → Verify equation balanced →
  Verify status bar → Close
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, \
        QStatusBar, QTreeView, QTableView, QMenuBar
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


def _seed_db() -> str:
    """Create a seeded temp DB with accounts, opening balances,
    and one month of activity for the E2E month-end close test."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    # Assets
    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    # Liabilities
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    # Income
    mgr.add_account("Wages", 4)
    mgr.add_account("Dividend Income", 4)
    # Expenses
    mgr.add_account("Groceries", 5)
    mgr.add_account("Rent", 5)
    mgr.add_account("Utilities", 5)
    # Equity — account 6 is retained earnings

    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}

    # Opening balances (via retained earnings)
    mgr.add_transaction(datetime(2026, 1, 1), "Opening", [
        Split(ids["HS Checking"], 10000000),
        Split(ids["Savings"], 2000000),
        Split(ids["Schwab Brokerage"], 5000000),
        Split(ids["Discover"], -530000),
        Split(6, -16470000),
    ])

    # June activity — income
    mgr.add_transaction(datetime(2026, 6, 1), "Paycheck", [
        Split(ids["Wages"], -300000),
        Split(ids["HS Checking"], 300000),
    ])
    mgr.add_transaction(datetime(2026, 6, 15), "Dividend", [
        Split(ids["Dividend Income"], -5000),
        Split(ids["HS Checking"], 5000),
    ])

    # June activity — expenses
    mgr.add_transaction(datetime(2026, 6, 2), "Rent", [
        Split(ids["Rent"], 150000),
        Split(ids["HS Checking"], -150000),
    ])
    mgr.add_transaction(datetime(2026, 6, 5), "Groceries", [
        Split(ids["Groceries"], 8500),
        Split(ids["HS Checking"], -8500),
    ])
    mgr.add_transaction(datetime(2026, 6, 20), "Electric bill", [
        Split(ids["Utilities"], 12000),
        Split(ids["HS Checking"], -12000),
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
#  E2E: Month-End Close Cycle
# ═══════════════════════════════════════════════════════════════════


class TestMonthEndClose:
    """One E2E acceptance test: full month-end close cycle.

    This is the OUTER LOOP that defines the complete close workflow.
    It validates:
      1. App opens with correct structure
      2. Pre-close balances (income, expenses, RE) are correct
      3. close_temps() resets income/expense to zero
      4. Retained earnings reflects net income
      5. Accounting equation remains balanced (A = L + E)
      6. Closing entries appear in the transaction table
    """

    def test_month_end_close(self, qt_app, db_path):
        """Full month-end close cycle through the PySide6 GUI."""
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI
        from ledger.gui_pyside.widgets import format_cents

        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager

            # Resolve account IDs by name
            ids = {a.name: aid for aid, a in m.accounts.items() if aid}
            checking       = ids["HS Checking"]
            savings        = ids["Savings"]
            brokerage      = ids["Schwab Brokerage"]
            discover       = ids["Discover"]
            wages          = ids["Wages"]
            div_income     = ids["Dividend Income"]
            groceries      = ids["Groceries"]
            rent           = ids["Rent"]
            utilities      = ids["Utilities"]

            # ════════════════════════════════════════════════
            #  Phase 1: Verify app structure
            # ════════════════════════════════════════════════

            assert window.windowTitle() == "Ledger — Double-Entry Accounting"

            menu_bar = window.menuBar()
            assert menu_bar is not None

            tabs = window.findChild(QTabWidget, "mainTabs")
            assert tabs is not None
            tab_labels = [tabs.tabText(i) for i in range(tabs.count())]
            assert "Ledger" in tab_labels

            tree = window.findChild(QTreeView, "accountTree")
            assert tree is not None
            tree_model = tree.model()
            assert tree_model is not None
            assert tree_model.rowCount() >= 1

            table = window.findChild(QTableView, "transactionTable")
            assert table is not None
            table_model = table.model()
            assert table_model is not None

            status = window.statusBar()
            assert status is not None

            # ════════════════════════════════════════════════
            #  Phase 2: Verify pre-close balances
            # ════════════════════════════════════════════════

            # Pre-close: income accounts use get_display_balance which
            # flips credit-normal accounts to positive
            assert m.get_display_balance(wages) == 300000, (
                f"Wages expected 300000, got {m.get_display_balance(wages)}"
            )
            assert m.get_display_balance(div_income) == 5000, (
                f"Dividends expected 5000, got {m.get_display_balance(div_income)}"
            )

            # Pre-close: expense accounts (debit-normal, no flip)
            net_income_expected = 300000 + 5000 - 150000 - 8500 - 12000  # = 134500
            actual_expenses = (
                m.get_display_balance(groceries) +
                m.get_display_balance(rent) +
                m.get_display_balance(utilities)
            )
            assert actual_expenses == 150000 + 8500 + 12000, (
                f"Total expenses expected 170500, got {actual_expenses}"
            )

            # Verify accounting equation before close
            eq_before = m.check_accounting_equation()
            assert eq_before["balanced"], (
                f"Equation unbalanced before close: {eq_before}"
            )

            # ════════════════════════════════════════════════
            #  Phase 3: Run month-end close
            # ════════════════════════════════════════════════

            re_before = m.get_display_balance(6)  # retained earnings
            m.close_temps()
            m.generate_ledger()
            window._refresh_all_internal()

            # ════════════════════════════════════════════════
            #  Phase 4: Verify post-close balances
            # ════════════════════════════════════════════════

            # Income accounts should be zeroed
            assert m.get_display_balance(wages) == 0, (
                f"Wages not zeroed: {m.get_display_balance(wages)}"
            )
            assert m.get_display_balance(div_income) == 0, (
                f"Dividend income not zeroed: {m.get_display_balance(div_income)}"
            )

            # Expense accounts should be zeroed
            assert m.get_display_balance(groceries) == 0
            assert m.get_display_balance(rent) == 0
            assert m.get_display_balance(utilities) == 0

            # Retained earnings should have increased by net income
            re_after = m.get_display_balance(6)
            re_change = re_after - re_before
            assert re_change == net_income_expected, (
                f"RE changed by {re_change}, expected {net_income_expected} "
                f"(net income = {net_income_expected})"
            )

            # ════════════════════════════════════════════════
            #  Phase 5: Equation still balanced
            # ════════════════════════════════════════════════

            eq_after = m.check_accounting_equation()
            assert eq_after["balanced"], (
                f"Equation unbalanced after close: {eq_after}"
            )

            # ════════════════════════════════════════════════
            #  Phase 6: Status bar shows balanced
            # ════════════════════════════════════════════════

            status_msg = status.currentMessage()
            assert "✓" in status_msg or "Balanced" in status_msg, (
                f"Status bar doesn't show balanced: '{status_msg}'"
            )

            # ════════════════════════════════════════════════
            #  Phase 7: Closing entries in the transaction table
            # ════════════════════════════════════════════════

            # There should be 5 closing entries (Wages, Div Income, Groceries,
            # Rent, Utilities) + 6 original transactions = 11 total
            table_model.refresh()
            txn_count = table_model.rowCount()
            assert txn_count == (6 + 5), (
                f"Expected 11 transactions (6 original + 5 closing), "
                f"got {txn_count}"
            )

        finally:
            window.close()
