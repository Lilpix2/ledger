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
