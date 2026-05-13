"""E2E tests for PySide6 ledger application — Report generation workflow.

Outer loop: Verify that all report types produce correct output
through the full application (menu → dialog → content).
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

import pytest

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


def _seed_with_reports() -> str:
    """Seed a DB with enough data for meaningful reports."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)
    mgr.add_account("Rent", 5)

    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}

    # Opening
    mgr.add_transaction(datetime(2026, 1, 1), "Opening", [
        Split(ids["HS Checking"], 10000000),
        Split(ids["Savings"], 2000000),
        Split(ids["Discover"], -530000),
        Split(6, -11470000),
    ])
    # Income
    mgr.add_transaction(datetime(2026, 6, 1), "Payday", [
        Split(ids["Wages"], -300000),
        Split(ids["HS Checking"], 300000),
    ])
    mgr.add_transaction(datetime(2026, 6, 15), "Payday", [
        Split(ids["Wages"], -300000),
        Split(ids["HS Checking"], 300000),
    ])
    # Expenses
    mgr.add_transaction(datetime(2026, 6, 2), "Rent", [
        Split(ids["Rent"], 150000),
        Split(ids["HS Checking"], -150000),
    ])
    mgr.add_transaction(datetime(2026, 6, 3), "Groceries", [
        Split(ids["Groceries"], 4500),
        Split(ids["HS Checking"], -4500),
    ])
    mgr.add_transaction(datetime(2026, 6, 10), "Groceries", [
        Split(ids["Groceries"], 7800),
        Split(ids["HS Checking"], -7800),
    ])
    mgr.generate_ledger()
    del mgr
    return path


@pytest.fixture
def db_path():
    path = _seed_with_reports()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


class TestReportGeneration:
    """One E2E test: generate all report types through the app.

    Uses the capture hook to intercept report text instead of
    actually opening dialogs (dialog rendering tested in component tests).
    """

    def _install_capture(self, mod):
        """Install the capture hook on a reports module."""
        storage: list[tuple[str, str]] = []
        setattr(mod, "_captured_reports", storage)
        return storage

    def test_generate_all_reports(self, qt_app, db_path):
        """Open app → generate Income Statement, Balance Sheet, Net Worth, Summary."""
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI
        import ledger.gui_pyside.reports as reports_mod

        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager

            # Install capture hook
            captured = self._install_capture(reports_mod)

            # ── 1. Net Worth ─────────────────────────────
            reports_mod.show_net_worth(window, m)
            assert len(captured) == 1
            title, text = captured[0]
            assert title == "Net Worth"
            assert "Assets:" in text
            assert "Liabilities:" in text
            assert "Net Worth:" in text
            assert "$" in text  # formatted USD values

            # ── 2. Account Summary ────────────────────────
            reports_mod.show_summary(window, m)
            assert len(captured) == 2
            title, text = captured[1]
            assert title == "Account Summary"
            assert any(g in text.upper() for g in ["ASSETS", "LIABILITIES", "EQUITY",
                                            "INCOME", "EXPENSES"])
            assert "Net Worth:" in text
            assert "Balanced" in text or "✓" in text

            # ── 3. Income Statement ───────────────────────
            reports_mod.show_income_stmt(window, m)
            assert len(captured) == 3
            title, text = captured[2]
            assert title == "Income Statement"
            assert "INCOME:" in text
            assert "EXPENSES:" in text
            assert "Net Income" in text or "Net Loss" in text

            # Verify income matches backend
            ni = m.gen_income_report()["net_income"]
            assert f"${abs(ni)/100:,.2f}" in text, (
                f"Net income {ni} not found in report"
            )

            # ── 4. Balance Sheet ──────────────────────────
            reports_mod.show_balance_sheet(window, m)
            assert len(captured) == 4
            title, text = captured[3]
            assert title == "Balance Sheet"
            assert "ASSETS:" in text
            assert "LIABILITIES:" in text
            assert "EQUITY:" in text

            # Verify balanced
            eq = m.check_accounting_equation()
            assert eq["balanced"]
            assert "Balanced" in text

            # ── 5. RE Statement ────────────────────────────
            reports_mod.show_re_statement(window, m)
            assert len(captured) == 5
            title, text = captured[4]
            assert title == "Retained Earnings Statement"
            assert "Beginning RE:" in text
            assert "Net Income:" in text
            assert "Ending RE:" in text

            # ── 6. About dialog ────────────────────────────
            reports_mod.show_about(window)
            assert len(captured) == 6
            title, text = captured[5]
            assert title == "About Ledger"
            assert "Double-Entry Accounting" in text

        finally:
            window.close()
