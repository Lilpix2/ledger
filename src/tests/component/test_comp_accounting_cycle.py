"""Component tests: full accounting cycle.

Tests the orchestration of multiple units working together:
  AccountManager + Journal + Ledger + Account.

Boundary: all internal logic kept, only DatabaseController is mocked (MockDB).
Black-box: tests through public interfaces (add_account, add_transaction,
  generate_ledger, check_accounting_equation, close_temps, gen_income_report).
Focus: flow orchestration, not individual method mechanics.
"""

import pytest
from datetime import datetime
from ledger.models.data_class import Split


# ═══════════════════════════════════════════════════════════════════
#  Setup component — reusable scenario builder
# ═══════════════════════════════════════════════════════════════════


class AccountingCycle:
    """Builds and exercises a complete accounting cycle on fast_manager.

    Component boundary: keeps AccountManager + Journal + Ledger + Account,
    mocks DatabaseController via fast_manager/fast_seeded fixture.
    """

    def __init__(self, mgr):
        self.mgr = mgr
        self.ids = {}

    def create_accounts(self):
        """Arrange: set up the chart of accounts."""
        m = self.mgr
        self.ids["checking"] = m.add_account("Checking", 1, account_subtype="checking")
        self.ids["savings"] = m.add_account("Savings", 1)
        self.ids["wages"] = m.add_account("Wages", 4)
        self.ids["groceries"] = m.add_account("Groceries", 5)
        self.ids["rent"] = m.add_account("Rent", 5)
        return self

    def enter_opening_balances(self):
        """Arrange: post opening balances."""
        i = self.ids
        self.mgr.add_transaction(
            datetime(2026, 1, 1), "Open",
            [Split(i["checking"], 10000000), Split(i["savings"], 500000),
             Split(6, -10500000)],
        )
        return self

    def earn_income(self):
        """Act: post several paychecks."""
        i = self.ids
        for day in [1, 15]:
            self.mgr.add_transaction(
                datetime(2026, 6, day), "Payday",
                [Split(i["wages"], -300000), Split(i["checking"], 300000)],
            )
        return self

    def pay_expenses(self):
        """Act: post rent and grocery expenses."""
        i = self.ids
        self.mgr.add_transaction(
            datetime(2026, 6, 2), "Rent",
            [Split(i["rent"], 200000), Split(i["checking"], -200000)],
        )
        self.mgr.add_transaction(
            datetime(2026, 6, 3), "Groceries",
            [Split(i["groceries"], 4500), Split(i["checking"], -4500)],
        )
        self.mgr.add_transaction(
            datetime(2026, 6, 10), "Groceries",
            [Split(i["groceries"], 7800), Split(i["checking"], -7800)],
        )
        return self

    def close_the_books(self):
        """Act: run closing entries."""
        self.mgr.close_temps()
        return self

    def rebuild(self):
        """Act: regenerate ledger from journal."""
        self.mgr.generate_ledger()
        return self

    def verify_balanced(self):
        """Assert: accounting equation holds."""
        eq = self.mgr.check_accounting_equation()
        assert eq["balanced"], f"Equation unbalanced: A={eq['assets']} L+E={eq['rhs']}"
        return self

    def verify_net_income(self, expected_cents):
        """Assert: income report matches expected."""
        inc = self.mgr.gen_income_report()
        assert inc["net_income"] == expected_cents, (
            f"NI {inc['net_income']} != expected {expected_cents}"
        )
        return self

    def verify_re_ending(self, expected_cents):
        """Assert: RE statement ending matches."""
        re = self.mgr.gen_retained_earnings_statement()
        assert re["ending_re"] == expected_cents, (
            f"RE ending {re['ending_re']} != expected {expected_cents}"
        )
        return self


# ═══════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════


class TestAccountingCycle:
    """Full accounting cycle scenarios."""

    def test_full_cycle_profit(self, fast_manager):
        """Open → earn → spend → close: profit scenario.

        Income: $6,000 ($3,000 × 2)
        Expenses: $2,123 (Rent $2,000 + Groceries $45 + $78)
        Net income: $3,877
        """
        cycle = AccountingCycle(fast_manager)
        (
            cycle.create_accounts()
            .enter_opening_balances()
            .rebuild()
            .verify_balanced()
            .earn_income()
            .pay_expenses()
            .rebuild()
            .verify_balanced()
            .verify_net_income(387700)  # $3,877
        )

    def test_full_cycle_close_preserves_balance(self, fast_manager):
        """After closing entries, equation stays balanced and RE includes NI."""
        cycle = AccountingCycle(fast_manager)
        (
            cycle.create_accounts()
            .enter_opening_balances()
            .earn_income()
            .pay_expenses()
            .rebuild()
        )

        ni_before = fast_manager.gen_income_report()["net_income"]
        re_before = fast_manager.get_display_balance(6)

        # Component action: close the books
        cycle.close_the_books().rebuild().verify_balanced()

        # Verify NI moved to RE
        re_after = fast_manager.get_display_balance(6)
        assert re_after == re_before + ni_before, (
            f"RE: {re_after} != {re_before} + {ni_before}"
        )
        # Income/expense accounts are zero
        for aid, acct in fast_manager.accounts.items():
            if acct.acct_type in ("INCOME", "EXPENSE"):
                assert acct.get_balance() == 0, (
                    f"{acct.name} not zeroed: {acct.get_balance()}"
                )
        cycle.verify_net_income(0)

    def test_full_cycle_net_loss(self, fast_manager):
        """Spend more than earned → net loss still balances.

        Income: $1,000
        Expenses: $3,000
        Net loss: -$2,000
        """
        i = {}
        m = fast_manager
        i["checking"] = m.add_account("Checking", 1)
        i["wages"] = m.add_account("Wages", 4)
        i["rent"] = m.add_account("Rent", 5)
        i["food"] = m.add_account("Food", 5)

        m.add_transaction(datetime(2026, 1, 1), "Open",
            [Split(i["checking"], 10000000), Split(6, -10000000)])
        m.add_transaction(datetime(2026, 6, 1), "Pay",
            [Split(i["wages"], -100000), Split(i["checking"], 100000)])
        m.add_transaction(datetime(2026, 6, 2), "Rent",
            [Split(i["rent"], 200000), Split(i["checking"], -200000)])
        m.add_transaction(datetime(2026, 6, 3), "Food",
            [Split(i["food"], 100000), Split(i["checking"], -100000)])
        m.generate_ledger()

        # Net loss
        inc = m.gen_income_report()
        assert inc["net_income"] == -200000, f"Expected net loss -200000, got {inc['net_income']}"
        assert inc["expenses_total"] > inc["income_total"]

        # Still balanced
        assert m.check_accounting_equation()["balanced"] is True

        # Close — still balanced
        m.close_temps()
        m.generate_ledger()
        assert m.check_accounting_equation()["balanced"] is True

    def test_dividends_reduce_retained_earnings(self, fast_manager):
        """Pay dividend → RE decreases by dividend amount."""
        i = {}
        m = fast_manager
        i["checking"] = m.add_account("Checking", 1)
        i["wages"] = m.add_account("Wages", 4)

        m.add_transaction(datetime(2026, 1, 1), "Open",
            [Split(i["checking"], 10000000), Split(6, -10000000)])
        m.add_transaction(datetime(2026, 6, 1), "Pay",
            [Split(i["wages"], -500000), Split(i["checking"], 500000)])
        m.generate_ledger()

        re_before = m.get_display_balance(6)

        # Pay dividend: debit dividends (9), credit checking
        m.add_transaction(datetime(2026, 7, 1), "Dividend",
            [Split(9, 50000), Split(i["checking"], -50000)])
        m.generate_ledger()

        m.close_temps()
        m.generate_ledger()

        re_after = m.get_display_balance(6)
        # RE = opening $100,000 + NI $5,000 - dividend $500 = $104,500
        assert re_after == 10450000, f"RE after dividend: {re_after}"
        assert m.check_accounting_equation()["balanced"] is True

    def test_reports_live_data_consistent(self, fast_manager):
        """All reports on the same data agree on net income."""
        cycle = AccountingCycle(fast_manager)
        cycle.create_accounts().enter_opening_balances().earn_income().pay_expenses()
        cycle.rebuild().verify_balanced()

        ni = fast_manager.gen_income_report()["net_income"]
        re = fast_manager.gen_retained_earnings_statement()
        bs = fast_manager.gen_balance_sheet()

        # RE ending = beginning + NI - dividends
        assert re["ending_re"] == re["beginning_re"] + ni
        # Balance sheet equity = RE + NI (pre-close)
        equity_names = {n for n, _ in bs["equity"]}
        assert "net income" in equity_names or re["ending_re"] == bs["total_equity"]
