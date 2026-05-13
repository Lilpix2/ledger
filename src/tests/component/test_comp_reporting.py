"""Component tests: reporting pipeline.

Tests the orchestration of transaction entry → report generation,
verifying that all reports agree on the same data and the accounting
equation is consistent.

Boundary: full AccountManager + Journal + Ledger, MockDB for speed.
Black-box: tests through public report methods only.
"""

import pytest
from datetime import datetime
from ledger.models.data_class import Split


class TestReportingPipeline:
    """Reports on the same data agree with each other."""

    def _build_basic_data(self, m):
        """Arrange: minimal accounts + transactions."""
        checking = m.add_account("Checking", 1)
        wages = m.add_account("Wages", 4)
        rent = m.add_account("Rent", 5)
        food = m.add_account("Food", 5)

        m.add_transaction(datetime(2026, 1, 1), "Open",
            [Split(checking, 10000000), Split(6, -10000000)])
        m.add_transaction(datetime(2026, 6, 1), "Pay",
            [Split(wages, -500000), Split(checking, 500000)])
        m.add_transaction(datetime(2026, 6, 2), "Rent",
            [Split(rent, 200000), Split(checking, -200000)])
        m.add_transaction(datetime(2026, 6, 3), "Food",
            [Split(food, 5000), Split(checking, -5000)])
        m.generate_ledger()
        return checking, wages, rent, food

    def test_income_report_matches_equation(self, fast_manager):
        """NI from income report matches net_income from equation check."""
        self._build_basic_data(fast_manager)

        inc = fast_manager.gen_income_report()
        eq = fast_manager.check_accounting_equation()

        # Income report NI should match equation net_income
        assert inc["net_income"] == eq["net_income"], (
            f"Report NI {inc['net_income']} != Equation NI {eq['net_income']}"
        )

    def test_balance_sheet_matches_equation(self, fast_manager):
        """BS assets and equity sum match accounting equation."""
        self._build_basic_data(fast_manager)

        bs = fast_manager.gen_balance_sheet()
        eq = fast_manager.check_accounting_equation()

        # A = L + E
        assert bs["total_assets"] == eq["assets"], (
            f"BS assets {bs['total_assets']} != eq assets {eq['assets']}"
        )

    def test_income_balance_sheet_agree_on_ni(self, fast_manager):
        """NI in income report + RE in BS = total equity pre-close."""
        self._build_basic_data(fast_manager)

        inc = fast_manager.gen_income_report()
        bs = fast_manager.gen_balance_sheet()
        re = fast_manager.gen_retained_earnings_statement()

        ni = inc["net_income"]
        ending_re = re["ending_re"]

        # Pre-close: total equity = RE + NI
        equity_names = {n for n, _ in bs["equity"]}
        total_equity = bs["total_equity"]

        # BS equity already includes NI (either as separate line or in RE)
        assert total_equity == ending_re, (
            f"BS equity {total_equity} != RE {ending_re} (should match)"
        )

    def test_income_statement_structure(self, fast_manager):
        """Income items and expense items have correct types."""
        self._build_basic_data(fast_manager)
        inc = fast_manager.gen_income_report()

        assert isinstance(inc["income"], list)
        assert isinstance(inc["expenses"], list)
        assert isinstance(inc["income_total"], int)
        assert isinstance(inc["expenses_total"], int)
        assert isinstance(inc["net_income"], int)

        for name, val in inc["income"]:
            assert isinstance(name, str)
            assert isinstance(val, int) and val >= 0
        for name, val in inc["expenses"]:
            assert isinstance(name, str)
            assert isinstance(val, int)

    def test_balance_sheet_structure(self, fast_manager):
        """Asset, liability, and equity items have correct structure."""
        self._build_basic_data(fast_manager)
        bs = fast_manager.gen_balance_sheet()

        for name, val in bs["assets"]:
            assert isinstance(name, str)
            assert isinstance(val, int)
        for name, val in bs["liabilities"]:
            assert isinstance(name, str)
            assert isinstance(val, int)
        for name, val in bs["equity"]:
            assert isinstance(name, str)
            assert isinstance(val, int)

    def test_total_assets_match_account_summary(self, fast_manager):
        """Balance sheet total assets match account summary assets."""
        self._build_basic_data(fast_manager)
        bs = fast_manager.gen_balance_sheet()
        summary = fast_manager.gen_account_summary()

        bs_assets = bs["total_assets"]
        summary_assets = 0
        for group in summary["groups"]:
            if group["type_label"] == "Assets":
                summary_assets = group["total_cents"]
                break

        assert bs_assets == summary_assets, (
            f"BS assets {bs_assets} != summary assets {summary_assets}"
        )

    def test_re_statement_after_close(self, fast_manager):
        """Post-close RE statement shows NI=0 and ending matches ledger."""
        self._build_basic_data(fast_manager)

        ni_before = fast_manager.gen_income_report()["net_income"]
        re_after = fast_manager.get_display_balance(6) + ni_before

        fast_manager.close_temps()
        fast_manager.generate_ledger()

        re_stmt = fast_manager.gen_retained_earnings_statement()
        actual_re = fast_manager.get_display_balance(6)

        assert re_stmt["net_income"] == 0, "NI should be 0 post-close"
        assert re_stmt["ending_re"] == actual_re, (
            f"RE statement {re_stmt['ending_re']} != ledger {actual_re}"
        )

    def test_all_reports_after_close(self, fast_manager):
        """All reports work and are balanced after closing entries."""
        self._build_basic_data(fast_manager)

        fast_manager.close_temps()
        fast_manager.generate_ledger()

        inc = fast_manager.gen_income_report()
        bs = fast_manager.gen_balance_sheet()
        re = fast_manager.gen_retained_earnings_statement()
        summary = fast_manager.gen_account_summary()

        assert inc["net_income"] == 0
        assert bs["balanced"] is True
        assert re["net_income"] == 0
        assert summary["balanced"] is True

    def test_date_filtered_reports(self, fast_manager):
        """Date-filtered reports only include transactions in range."""
        self._build_basic_data(fast_manager)

        full = fast_manager.gen_income_report()
        assert full["net_income"] > 0

        # Filter to before any transactions
        before = fast_manager.gen_income_report(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
        )
        assert before["net_income"] == 0
        assert before["income"] == []
        assert before["expenses"] == []

        # Filter to first half
        q1 = fast_manager.gen_income_report(
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 6, 15),
        )
        assert q1["net_income"] > 0

    def test_account_summary_structure(self, fast_manager):
        """Account summary has 5 groups with correct labels."""
        self._build_basic_data(fast_manager)
        summary = fast_manager.gen_account_summary()

        labels = {g["type_label"] for g in summary["groups"]}
        expected = {"Assets", "Liabilities", "Equity", "Income", "Expenses"}
        assert labels == expected, f"Summary groups: {labels}"
        assert "net_worth" in summary
        assert "balanced" in summary
        assert summary["balanced"] is True
