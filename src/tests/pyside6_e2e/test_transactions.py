"""E2E tests for PySide6 ledger application — Transaction CRUD lifecycle.

Outer loop: One acceptance test per feature.
Build inner loop components (unit/component tests) until these pass.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, \
        QStatusBar, QTreeView, QTableView, QMenuBar, QPushButton, QLineEdit
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.constants import DATE_STR


def _seed_db() -> str:
    """Create a seeded temp DB with accounts but NO transactions.

    We want a clean slate so the CRUD test can create its own.
    """
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)
    mgr.add_account("Rent", 5)

    # Opening balances — just enough to have cash and debt
    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}
    mgr.add_transaction(datetime(2026, 1, 1), "Opening", [
        Split(ids["HS Checking"], 10000000),
        Split(ids["Savings"], 500000),
        Split(ids["Discover"], -530000),
        Split(6, -9970000),
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
#  E2E: Transaction CRUD
# ═══════════════════════════════════════════════════════════════════


class TestTransactionCRUD:
    """One E2E test: full transaction lifecycle through the app.

    Outer loop: Create → Verify in table → Verify balances →
    Edit → Verify update → Delete → Verify reverted → Balanced.
    """

    def test_transaction_crud(self, qt_app, db_path):
        """Complete transaction CRUD lifecycle."""
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI
        from ledger.gui_pyside.widgets import format_cents
        from PySide6.QtWidgets import QTableView

        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager

            # Resolve account IDs
            checking = next(aid for aid, a in m.accounts.items()
                           if a.name == "HS Checking")
            groceries = next(aid for aid, a in m.accounts.items()
                            if a.name == "Groceries")

            checking_bal_before = m.get_display_balance(checking)
            groceries_bal_before = m.get_display_balance(groceries)

            # ── 1. CREATE a transaction ────────────────────
            txn_id = m.add_transaction(
                datetime(2026, 7, 15), "E2E Grocery Run",
                [Split(groceries, 5000), Split(checking, -5000)],
            )
            m.generate_ledger()
            window._table_model.refresh()
            window._refresh_status()

            # Verify balances updated
            assert m.get_display_balance(checking) == checking_bal_before - 5000
            assert m.get_display_balance(groceries) == groceries_bal_before + 5000

            # Verify table shows the transaction
            table = window.findChild(QTableView, "transactionTable")
            assert table is not None
            table_model = table.model()
            assert table_model is not None
            assert table_model.rowCount() >= 2  # Opening + new txn

            # Verify status bar updates
            status = window.statusBar()
            assert status is not None
            status_msg = status.currentMessage()
            assert "✓" in status_msg or status_msg != ""

            # ── 2. READ — verify transaction details ───────
            txn = m.journal.transactions.get(txn_id)
            assert txn is not None
            assert txn.description == "E2E Grocery Run"
            assert len(txn.splits) == 2

            # ── 3. UPDATE the transaction ──────────────────
            # For now, update through manager (dialog tested in component)
            m.delete_transaction(txn_id)
            new_txn_id = m.add_transaction(
                datetime(2026, 7, 15), "E2E Groceries Updated",
                [Split(groceries, 7800), Split(checking, -7800)],
            )
            m.generate_ledger()
            window._table_model.refresh()
            window._refresh_status()

            # Verify old txn gone, new txn present
            assert txn_id not in m.journal.transactions
            assert new_txn_id in m.journal.transactions
            updated = m.journal.transactions[new_txn_id]
            assert updated.description == "E2E Groceries Updated"

            # Balances reflect the updated amount
            assert m.get_display_balance(checking) == checking_bal_before - 7800
            assert m.get_display_balance(groceries) == groceries_bal_before + 7800

            # ── 4. DELETE the transaction ──────────────────
            m.delete_transaction(new_txn_id)
            m.generate_ledger()
            window._table_model.refresh()
            window._refresh_status()

            assert new_txn_id not in m.journal.transactions

            # Balances revert to pre-transaction state
            assert m.get_display_balance(checking) == checking_bal_before
            assert m.get_display_balance(groceries) == groceries_bal_before

            # ── 5. Equation stays balanced ─────────────────
            eq = m.check_accounting_equation()
            assert eq["balanced"], "Equation unbalanced after Transaction CRUD"

        finally:
            window.close()
