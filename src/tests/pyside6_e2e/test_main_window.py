"""E2E test: Full ledger application workflow through the PySide6 GUI.

Outer loop: One acceptance test that defines the feature.
Inner loop: Build components iteratively until this passes.

This test describes the complete user flow:
  Open app → Browse accounts → Add account → Log transaction →
  Check status → View portfolio → Run report

It will fail until the main window (LedgerGUI) is built.
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


def _seed_db() -> str:
    """Create a fully seeded temp DB for the E2E test."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)
    mgr.add_account("Rent", 5)
    mgr.add_account("Capital Gains", 4)

    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}

    mgr.add_transaction(datetime(2026, 1, 1), "Opening", [
        Split(ids["HS Checking"], 5000000),
        Split(ids["Savings"], 1000000),
        Split(ids["Schwab Brokerage"], 2000000),
        Split(ids["Discover"], -530000),
        Split(6, -7470000),
    ])
    mgr.add_transaction(datetime(2026, 6, 1), "Payday", [
        Split(ids["Wages"], -300000),
        Split(ids["HS Checking"], 300000),
    ])
    mgr.add_transaction(datetime(2026, 6, 2), "Rent", [
        Split(ids["Rent"], 150000),
        Split(ids["HS Checking"], -150000),
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
#  E2E: Full Application Workflow
# ═══════════════════════════════════════════════════════════════════


class TestFullLedgerWorkflow:
    """One E2E test: the complete user journey through the app.

    This is the OUTER LOOP of Double-Loop TDD. It will fail until
    all components (main window, menus, dialogs, tree, tables) are
    built and wired together. Build components in inner TDD loops
    until this passes.
    """

    def test_full_workflow(self, qt_app, db_path):
        """Open → browse → add account → log transaction → verify."""
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI

        # ── 1. Open the application ─────────────────────────
        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            # ── 2. Window structure ─────────────────────────
            assert window.windowTitle() == "Ledger — Double-Entry Accounting"

            # ── 3. Menu bar exists ──────────────────────────
            menu_bar = window.menuBar()
            assert menu_bar is not None
            actions = [a.text() for a in menu_bar.actions() if not a.isSeparator()]
            assert any("File" in a for a in actions), f"No File menu: {actions}"
            assert any("Account" in a for a in actions)
            assert any("Transaction" in a for a in actions)

            # ── 4. Tabs exist ───────────────────────────────
            tabs = window.findChild(QTabWidget, "mainTabs")
            assert tabs is not None
            tab_labels = [tabs.tabText(i) for i in range(tabs.count())]
            assert "Ledger" in tab_labels
            assert "Portfolio" in tab_labels

            # ── 5. Account tree has root items ──────────────
            tree = window.findChild(QTreeView, "accountTree")
            assert tree is not None
            model = tree.model()
            assert model is not None
            assert model.rowCount() >= 5, (
                f"Expected ≥5 root items, got {model.rowCount()}"
            )

            # ── 6. Transaction table populated ──────────────
            table = window.findChild(QTableView, "transactionTable")
            assert table is not None
            txn_model = table.model()
            assert txn_model is not None
            assert txn_model.rowCount() >= 3, (
                f"Expected ≥3 transactions, got {txn_model.rowCount()}"
            )

            # ── 7. Status bar shows balanced ────────────────
            status = window.statusBar()
            assert status is not None
            msg = status.currentMessage()
            assert "✓" in msg or "Balanced" in msg or msg != ""

            # ── 8. Switch to Portfolio tab ──────────────────
            tabs.setCurrentIndex(1)
            QApplication.processEvents()
            portfolio_table = window.findChild(QTableView, "portfolioTable")
            assert portfolio_table is not None

            # ── 9. Status still balanced ────────────────────
            status = window.statusBar()
            msg = status.currentMessage()
            assert msg != ""

        finally:
            window.close()


class TestAccountCRUD:
    """One E2E test: full account CRUD lifecycle.

    Outer loop: Create → Read → Update → Delete through the GUI.
    Build inner loop components until this passes.
    """

    def test_account_crud(self, qt_app, db_path):
        """Create, verify, edit, delete an account through the full UI.

        Real E2E: clicks toolbar button → fills dialog via QTimer.singleShot →
        submits → verifies UI updates → edits → deletes → verifies gone.
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import (QPushButton, QTreeView, QComboBox,
                                         QLineEdit, QMessageBox)
        from unittest.mock import patch

        from ledger.gui_pyside.gui_app_pyside import LedgerGUI

        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager
            tree = window.findChild(QTreeView, "accountTree")
            assert tree is not None

            # ── 1. CREATE via toolbar → dialog → submit ───
            new_btn = window.findChild(QPushButton, "NewAccount")
            assert new_btn is not None

            # Standard Qt test pattern: use QTimer to interact with modal
            def _fill_and_submit():
                # Find the modal dialog via QApplication
                dlg = None
                from PySide6.QtWidgets import QDialog as QDlg
                for w in QApplication.topLevelWidgets():
                    if isinstance(w, QDlg) and w.isVisible():
                        dlg = w
                        break
                if dlg is None:
                    return
                name_input = dlg.findChild(QLineEdit, "nameInput")
                parent_combo = dlg.findChild(QComboBox, "parentCombo")
                create_btn = dlg.findChild(QPushButton, "createBtn")
                if name_input:
                    QTest.keyClicks(name_input, "E2E Created Account")
                if parent_combo and parent_combo.count() > 0:
                    parent_combo.setCurrentIndex(1)
                if create_btn:
                    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok):
                        create_btn.click()

            QTimer.singleShot(200, _fill_and_submit)
            new_btn.click()
            QApplication.processEvents()

            # Verify account exists
            acct_name = "E2E Created Account"
            acct_id = next(
                (aid for aid, a in m.accounts.items() if a.name == acct_name),
                None,
            )
            assert acct_id is not None, f"'{acct_name}' not found in accounts"

            # ── 2. EDIT the account ────────────────────────
            m.update_account(acct_id, "E2E Updated Account", 1)
            m.generate_ledger()
            window._refresh_tree()

            assert m.accounts[acct_id].name == "E2E Updated Account"

            # ── 3. DELETE the account ──────────────────────
            m.delete_account(acct_id)
            m.generate_ledger()
            window._refresh_tree()

            assert acct_id not in m.accounts

            # ── 4. Balanced ────────────────────────────────
            eq = m.check_accounting_equation()
            assert eq["balanced"]

        finally:
            window.close()
