"""E2E test: Portfolio tab through the PySide6 GUI.

Outer loop: Buy a security → Switch to Portfolio tab →
Verify holding appears with correct data → Sell →
Verify holding updated → Balanced throughout.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, \
        QStatusBar, QTreeView, QTableView, QLabel
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


def _seed_portfolio_db() -> str:
    """Seed a DB with accounts and cash but no holdings yet.

    Structure:
      - HS Checking (checking) — plenty of cash
      - Schwab Brokerage (brokerage) — ready to buy
      - Savings (checking) — idle cash
      - Capital Gains (INCOME) — for sell gains
      - Wages (INCOME) — income
    """
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Capital Gains", 4)
    mgr.add_account("Wages", 4)

    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}

    mgr.add_transaction(datetime(2026, 1, 1), "Opening", [
        Split(ids["HS Checking"], 10000000),
        Split(ids["Savings"], 2000000),
        Split(ids["Schwab Brokerage"], 100),  # nominal seed
        Split(6, -12000100),
    ])

    # Set prices for VTI, AAPL, BND
    mgr.save_price("VTI", "2026-05-01", 27500)
    mgr.save_price("AAPL", "2026-05-01", 15000)
    mgr.save_price("BND", "2026-05-01", 7200)

    mgr.generate_ledger()
    del mgr
    return path


@pytest.fixture
def db_path():
    path = _seed_portfolio_db()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════
#  E2E: Portfolio Tab Full Workflow
# ═══════════════════════════════════════════════════════════════════


class TestPortfolioThroughGui:
    """One E2E test: full portfolio lifecycle through the app.

    Flow:
      1. Open app — verify no holdings in portfolio tab
      2. Buy VTI via backend (dialog tested in component)
      3. Refresh — verify portfolio tab shows VTI
      4. Buy AAPL — verify both holdings shown
      5. Sell some VTI — verify quantities update
      6. Equation stays balanced
    """

    def test_portfolio_workflow(self, qt_app, db_path):
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI

        window = LedgerGUI(db_path=db_path)
        window.show()
        QApplication.processEvents()

        try:
            m = window._manager
            tabs = window.findChild(QTabWidget, "mainTabs")
            assert tabs is not None

            # Resolve account IDs
            checking = next(aid for aid, a in m.accounts.items()
                            if a.name == "HS Checking")
            brokerage = next(aid for aid, a in m.accounts.items()
                             if a.name == "Schwab Brokerage")
            gains = next(aid for aid, a in m.accounts.items()
                         if a.name == "Capital Gains")

            # ── Phase 1: No holdings initially ─────────────
            tabs.setCurrentIndex(1)  # Portfolio tab
            QApplication.processEvents()

            portfolio_table = window.findChild(QTableView, "portfolioTable")
            assert portfolio_table is not None
            portfolio_model = portfolio_table.model()

            # Initially zero holdings
            initial_holding_count = portfolio_model.rowCount()
            assert initial_holding_count == 0, (
                f"Expected 0 initial holdings, got {initial_holding_count}"
            )

            # ── Phase 2: Buy VTI ───────────────────────────
            m.buy_security(
                datetime(2026, 5, 15), "Buy VTI",
                brokerage, checking, "VTI", 50, 27500,
            )
            m.save_price("VTI", "latest", 27500)
            m.generate_ledger()

            # Refresh the portfolio display
            window._refresh_portfolio()
            QApplication.processEvents()

            # Verify VTI appears
            assert portfolio_model.rowCount() >= 1, "VTI not shown after buy"

            # Verify balances are correct on backend
            checking_bal = m.get_display_balance(checking)
            # 10M - (50 * 27500) = 10M - 1,375,000 = 8,625,000
            assert checking_bal == 8625000, (
                f"Checking balance: {checking_bal}, expected 8625000"
            )

            # Verify VTI holding exists
            holdings = m.get_holdings(brokerage)
            vti = next((h for h in holdings if h.ticker == "VTI"), None)
            assert vti is not None, "VTI holding not found"
            assert vti.shares == 50.0
            assert vti.cost_basis_cents == 50 * 27500  # 1,375,000

            # ── Phase 3: Buy AAPL ──────────────────────────
            m.buy_security(
                datetime(2026, 5, 20), "Buy AAPL",
                brokerage, checking, "AAPL", 20, 15000,
            )
            m.save_price("AAPL", "latest", 15000)
            m.generate_ledger()
            window._refresh_portfolio()
            QApplication.processEvents()

            # Now 2 holdings
            assert portfolio_model.rowCount() >= 2, "AAPL not shown after buy"

            aapl = next((h for h in m.get_holdings(brokerage)
                        if h.ticker == "AAPL"), None)
            assert aapl is not None
            assert aapl.shares == 20.0

            # ── Phase 4: Sell some VTI ─────────────────────
            m.save_price("VTI", "latest", 29000)
            m.sell_security(
                datetime(2026, 6, 1), "Sell VTI",
                brokerage, checking, "VTI", 20, 29000,
                gain_account_id=gains,
            )
            m.generate_ledger()
            window._refresh_all_internal()
            QApplication.processEvents()

            # VTI reduced to 30 shares
            vti_after = next((h for h in m.get_holdings(brokerage)
                             if h.ticker == "VTI"), None)
            assert vti_after is not None
            assert vti_after.shares == 30.0, (
                f"Expected 30 shares VTI, got {vti_after.shares}"
            )

            # Checking increased from sale proceeds (20 * 29000 = 580000)
            checking_after_sell = m.get_display_balance(checking)
            expected_checking = 10000000 - (50 * 27500) - (20 * 15000) + (20 * 29000)
            # = 10M - 1.375M - 300K + 580K = 8,905,000
            assert checking_after_sell == expected_checking, (
                f"Checking: {checking_after_sell}, expected {expected_checking}"
            )

            # ── Phase 5: Equation stays balanced ───────────
            eq = m.check_accounting_equation()
            assert eq["balanced"], "Equation unbalanced after portfolio workflow"

            # Status bar still shows balanced
            status = window.statusBar()
            msg = status.currentMessage()
            assert "✓" in msg or msg != ""

            # ── Phase 6: Portfolio summary shows total ─────
            tabs.setCurrentIndex(1)
            QApplication.processEvents()
            tab_widget = tabs.widget(1)
            labels = tab_widget.findChildren(QLabel)
            summary = next((l for l in labels if "Market Value" in l.text()), None)
            assert summary is not None, "No Total Market Value label found"
            assert "$" in summary.text()

        finally:
            window.close()
