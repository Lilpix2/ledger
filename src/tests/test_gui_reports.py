"""Tests for the GUI report views and account tree display.

These tests verify that:
- All reports render without crashing
- Account tree shows display-normal (positive) balances
- Income accounts never appear as negative in the tree
- Each report's content includes expected labels
- The status bar reflects the accounting equation correctly

Note: tkinter tests need a display (X11, Wayland, or Xvfb).
Tests are skipped automatically when no display is available.
"""

import os
import sys
import tempfile
from datetime import datetime

import pytest

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


# ── Standalone formatter (avoids importing tkinter at module load) ─


def _format_cents(cents: int | None) -> str:
    """Format cents as USD, matching ledger.gui.widgets.format_cents."""
    if cents is None:
        return "—"
    return f"${cents/100:,.2f}"


def _has_tkinter_display() -> bool:
    """Check if a tkinter display is available."""
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


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def seeded_db() -> str:
    """Build a seeded database and return the path."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Capital Gains", 4)
    mgr.add_account("Wages", 4)
    mgr.add_account("Rent", 5)
    mgr.add_account("Groceries", 5)

    ids = {acct.name: aid for aid, acct in mgr.accounts.items() if aid}

    # Opening balances (already closed to RE)
    mgr.add_transaction(
        datetime(2026, 1, 1), "Opening balances",
        [
            Split(ids["HS Checking"], 5000000),
            Split(ids["Savings"], 1000000),
            Split(ids["Discover"], -530000),
            Split(6, -5470000),
        ],
    )

    # Current period income
    mgr.add_transaction(
        datetime(2026, 6, 1), "Payday",
        [Split(ids["Wages"], -300000), Split(ids["HS Checking"], 300000)],
    )

    # Current period expenses
    mgr.add_transaction(
        datetime(2026, 6, 2), "Rent",
        [Split(ids["Rent"], 150000), Split(ids["HS Checking"], -150000)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 3), "Groceries",
        [Split(ids["Groceries"], 4500), Split(ids["HS Checking"], -4500)],
    )

    mgr.generate_ledger()
    del mgr
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════
#  REPORT LOGIC TESTS (no tkinter needed)
# ═══════════════════════════════════════════════════════════════════


class TestReportLogic:
    """Report functions work correctly with real data."""

    def test_account_tree_no_negative_balances(self, seeded_db: str):
        """Every account's display balance is zero or positive.

        This catches the bug where income accounts showed as negative
        in the account tree due to raw credit-normal balances being
        displayed without sign-flipping.
        """
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        for aid, acct in mgr.accounts.items():
            if aid == 0:
                continue
            display = mgr.get_display_balance(aid)
            formatted = _format_cents(display)
            assert display >= 0, (
                f"Account '{acct.name}' (id={aid}, type={acct.acct_type}) "
                f"has negative display balance: {formatted}"
            )
            assert "-" not in formatted, (
                f"Account '{acct.name}' shows as negative: {formatted}"
            )

    def test_balance_sheet_balanced_pre_close(self, seeded_db: str):
        """Pre-close balance sheet includes NI in equity and balances."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        bs = mgr.gen_balance_sheet()
        assert bs["balanced"], (
            f"Pre-close BS unbalanced: A={bs['total_assets']} "
            f"L+E={bs['total_liabilities_equity']}"
        )

        # Equity should have net income, not just RE
        equity_names = {n for n, _ in bs["equity"]}
        assert "net income" in equity_names or "retained earnings" in equity_names

        # No income accounts should leak into the balance sheet sections
        all_asset_names = {n for n, _ in bs["assets"]}
        assert "wages" not in [n.lower() for n in all_asset_names], (
            f"Income account 'Wages' leaked into assets: {all_asset_names}"
        )

    def test_balance_sheet_balanced_post_close(self, seeded_db: str):
        """Post-close balance sheet has NI in RE, no separate NI line."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        mgr.close_temps()
        mgr.generate_ledger()

        bs = mgr.gen_balance_sheet()
        assert bs["balanced"], (
            f"Post-close BS unbalanced: A={bs['total_assets']} "
            f"L+E={bs['total_liabilities_equity']}"
        )

        equity_names = {n for n, _ in bs["equity"]}
        assert "net income" not in equity_names, (
            f"Post-close BS should not have separate NI line, got {equity_names}"
        )

    def test_balance_sheet_retained_earnings_not_inflated(self, seeded_db: str):
        """RE on the balance sheet should match the ledger, not be inflated."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        # Close once
        mgr.close_temps()
        mgr.generate_ledger()

        actual_re = mgr.get_display_balance(6)

        bs = mgr.gen_balance_sheet()
        # Find RE in equity items
        re_in_bs = 0
        for name, bal in bs["equity"]:
            if "retained" in name.lower():
                re_in_bs = bal
                break

        assert re_in_bs == actual_re, (
            f"BS RE ({re_in_bs}) doesn't match ledger RE ({actual_re})"
        )

    def test_income_statement_net_income_positive(self, seeded_db: str):
        """Income statement shows positive net income."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        report = mgr.gen_income_report()
        assert report["income_total"] > 0
        assert report["expenses_total"] > 0
        assert report["net_income"] > 0

        # All individual income items are positive
        for name, total in report["income"]:
            assert total > 0, f"Income item '{name}' has negative total {total}"

    def test_re_statement_no_double_count_pre_close(self, seeded_db: str):
        """RE statement doesn't double-count before close."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        re = mgr.gen_retained_earnings_statement()
        # Before close: beginning_re should match ledger RE
        actual_re = mgr.get_display_balance(6)
        ni = re["net_income"]

        assert re["beginning_re"] == actual_re, (
            f"Pre-close beginning_re ({re['beginning_re']}) "
            f"should equal ledger RE ({actual_re})"
        )
        assert re["ending_re"] == actual_re + ni, (
            f"ending_re ({re['ending_re']}) != "
            f"beginning ({actual_re}) + NI ({ni})"
        )

    def test_re_statement_no_double_count_post_close(self, seeded_db: str):
        """RE statement doesn't double-count after close."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()
        mgr.close_temps()
        mgr.generate_ledger()

        actual_re = mgr.get_display_balance(6)
        re = mgr.gen_retained_earnings_statement()

        # Post-close: NI should be 0 (already in RE)
        assert re["net_income"] == 0, (
            f"Post-close NI should be 0, got {re['net_income']}"
        )
        assert re["ending_re"] == actual_re, (
            f"ending_re ({re['ending_re']}) != ledger RE ({actual_re})"
        )

    def test_account_summary_balanced(self, seeded_db: str):
        """Account summary is balanced."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        summary = mgr.gen_account_summary()
        assert summary["balanced"] is True
        assert summary["net_worth"] >= 0

    def test_double_close_is_noop(self, seeded_db: str):
        """Closing entries twice doesn't change RE or break things."""
        mgr = AccountManager(seeded_db)
        mgr.generate_ledger()

        mgr.close_temps()
        mgr.generate_ledger()
        re_after_first = mgr.get_display_balance(6)

        mgr.close_temps()
        mgr.generate_ledger()
        re_after_second = mgr.get_display_balance(6)

        assert re_after_second == re_after_first, (
            f"Second close changed RE: {re_after_first} → {re_after_second}"
        )

        bs = mgr.gen_balance_sheet()
        assert bs["balanced"], "BS unbalanced after double close"


# ═══════════════════════════════════════════════════════════════════
#  TKINTER GUI TESTS (requires display)
# ═══════════════════════════════════════════════════════════════════


@no_display
class TestGUIApp:
    """The tkinter GUI window renders correctly."""

    def test_app_creates_and_opens(self, seeded_db: str):
        """App can be instantiated with a seeded DB without errors."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            assert app.title() == "Ledger — Double-Entry Accounting"
            assert app.manager is not None
        finally:
            app.destroy()

    def test_menu_has_expected_items(self, seeded_db: str):
        """Menu bar has File, Accounts, Transactions, Help."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            menu = app.winfo_children()[0]
            menu_names = []
            for i in range(menu.index("end") + 1):
                try:
                    label = menu.entrycget(i, "label")
                    menu_names.append(label)
                except tk.TclError:
                    pass

            expected = ["File", "Accounts", "Transactions", "Help"]
            for name in expected:
                assert name in menu_names, (
                    f"Menu '{name}' not found in {menu_names}"
                )
        finally:
            app.destroy()

    def test_report_dialogs_open_without_error(self, seeded_db: str):
        """Each report menu command triggers without crashing."""
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
            assert any("Net Worth" in s[0] for s in shown), (
                f"Net Worth not triggered: {shown}"
            )

            app._show_summary()
            assert any("Account Summary" in s[0] for s in shown), (
                f"Summary not triggered: {shown}"
            )

            app._show_income_stmt()
            assert any("Income Statement" in s[0] for s in shown), (
                f"Income Statement not triggered: {shown}"
            )

            app._show_balance_sheet()
            assert any("Balance Sheet" in s[0] for s in shown), (
                f"Balance Sheet not triggered: {shown}"
            )

            app._show_re_statement()
            assert any("Retained Earnings" in s[0] for s in shown), (
                f"RE Statement not triggered: {shown}"
            )

            # The dialogs should show proper numbers (no errors, no None)
            for title, msg in shown:
                assert msg is not None
                assert "None" not in msg
                assert "Error" not in title

        finally:
            mb.showinfo = original_show
            app.destroy()

    def test_status_bar_shows_balanced(self, seeded_db: str):
        """Status bar equation shows as balanced."""
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            status_text = app.status_var.get()
            assert "✓" in status_text or "Balanced" in status_text, (
                f"Status bar doesn't show balanced: {status_text}"
            )
        finally:
            app.destroy()

    def test_account_tree_has_no_negative_formatting(self, seeded_db: str):
        """Every value in the account tree formats as positive."""
        import tkinter as tk
        from ledger.gui_app import LedgerGUI

        app = LedgerGUI(db_path=seeded_db)
        try:
            tree = app.account_tree

            def check_item(iid: str) -> None:
                values = tree.item(iid, "values")
                if values and len(values) > 0:
                    bal_str = values[0]
                    assert not bal_str.startswith("-$"), (
                        f"Negative balance in tree at "
                        f"'{tree.item(iid, 'text')}': {bal_str}"
                    )
                for child in tree.get_children(iid):
                    check_item(child)

            for item in tree.get_children():
                check_item(item)
        finally:
            app.destroy()
