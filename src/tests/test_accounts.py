"""Unit tests: account CRUD, subtypes, hierarchy, and tree operations."""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


class TestAccountCreation:
    """Creating accounts with various options."""

    def test_create_default(self, manager: AccountManager):
        """Default accounts load on a fresh DB."""
        assert 0 in manager.accounts  # root
        assert len(manager.accounts) == 11  # root + 5 parents + 5 defaults

    def test_create_with_name(self, manager: AccountManager):
        aid = manager.add_account("My Checking", 1)
        assert aid > 0
        assert manager.accounts[aid].name == "My Checking"

    def test_create_with_subtype(self, manager: AccountManager):
        aid = manager.add_account("My Checking", 1, account_subtype="checking")
        assert manager.accounts[aid].account_subtype == "checking"

    def test_create_with_invalid_subtype(self, manager: AccountManager):
        with pytest.raises(ValueError, match="Invalid account_subtype"):
            manager.add_account("Bad", 1, account_subtype="not_a_subtype")

    def test_duplicate_name_raises(self, manager: AccountManager):
        manager.add_account("Test", 1)
        with pytest.raises(ValueError, match="already exists"):
            manager.add_account("Test", 1)

    def test_create_contra(self, manager: AccountManager):
        aid = manager.add_account("Acc Depreciation", 1, is_contra=True)
        assert manager.accounts[aid].is_contra is True

    def test_type_inherited_from_parent(self, manager: AccountManager):
        aid = manager.add_account("My Expense", 5)  # parent 5 = Expenses
        assert manager.accounts[aid].acct_type == "EXPENSE"

    def test_create_under_root(self, manager: AccountManager):
        """Top-level accounts (parent 0) get type ASSET if not specified."""
        aid = manager.add_account("NewTopLevel", 0, "LIABILITY")
        assert manager.accounts[aid].acct_type == "LIABILITY"
        assert manager.accounts[aid].parent == 0


class TestAccountQueries:
    """Querying account trees, descendants, and parents."""

    def test_build_tree(self, seeded_manager: AccountManager, ids: dict):
        tree = seeded_manager.build_tree()
        assert 1 in tree  # Assets has children
        assert 0 in tree  # Root has top-level children

    def test_get_descendants(self, seeded_manager: AccountManager, ids: dict):
        descendants = seeded_manager.get_descendant_ids(1)  # Assets
        assert ids["HS Checking"] in descendants
        assert ids["Schwab Brokerage"] in descendants
        assert 1 in descendants  # self

    def test_get_top_level_parent(self, seeded_manager: AccountManager, ids: dict):
        top = seeded_manager.get_top_level_parent(ids["HS Checking"])
        assert top == 1  # Assets

    def test_top_level_parent_of_root(self, manager: AccountManager):
        assert manager.get_top_level_parent(0) == 0

    def test_top_level_parent_of_parent(self, manager: AccountManager):
        assert manager.get_top_level_parent(1) == 1  # Assets

    def test_aggregated_balance(self, seeded_manager: AccountManager, ids: dict):
        """Assets aggregated balance should equal liab + equity."""
        assets = seeded_manager.aggregated_balance(1)
        liab = seeded_manager.aggregated_balance(2)
        equity = seeded_manager.aggregated_balance(3)
        assert assets == -(liab + equity)  # raw: assets +, liab/equity -


class TestDisplayBalance:
    """Display-normal balances for different account types."""

    def test_liability_positive(self, seeded_manager: AccountManager, ids: dict):
        """Liabilities display as positive despite raw negative balance."""
        raw = seeded_manager.aggregated_balance(ids["Discover"])
        display = seeded_manager.get_display_balance(ids["Discover"])
        assert raw <= 0  # raw is negative for credit-normal
        assert display >= 0  # display is positive
        assert display == -raw

    def test_asset_positive(self, seeded_manager: AccountManager, ids: dict):
        """Assets display as positive (raw is already positive)."""
        raw = seeded_manager.aggregated_balance(ids["HS Checking"])
        display = seeded_manager.get_display_balance(ids["HS Checking"])
        assert display == raw

    def test_is_debit_normal(self, manager: AccountManager):
        assert manager.is_debit_normal(1) is True   # Asset
        assert manager.is_debit_normal(2) is False  # Liability
        assert manager.is_debit_normal(3) is False  # Equity
        assert manager.is_debit_normal(4) is False  # Income
        assert manager.is_debit_normal(5) is True   # Expense


class TestFinancialReports:
    """Income statement, balance sheet, RE statement."""

    def test_checking_equation(self, seeded_manager: AccountManager):
        eq = seeded_manager.check_accounting_equation()
        assert eq["balanced"] is True, "Accounting equation must balance"
        assert eq["net_worth"] >= 0, "Net worth should be positive"

    def test_income_report(self, seeded_manager: AccountManager):
        # Sell a VTI with gain to generate income
        ids = seeded_manager.account_ids
        seeded_manager.sell_security(
            datetime(2026, 5, 1), "Sell VTI",
            ids["Schwab Brokerage"], ids["HS Checking"],
            "VTI", 10, 29500,
            gain_account_id=ids["Capital Gains"],
        )
        seeded_manager.generate_ledger()
        report = seeded_manager.gen_income_report()
        assert report["income_total"] > 0  # Realized gains
        assert report["net_income"] > 0

    def test_retained_earnings(self, seeded_manager: AccountManager):
        re = seeded_manager.gen_retained_earnings_statement()
        assert "beginning_re" in re
        assert "ending_re" in re
        assert "net_income" in re

    def test_balance_sheet(self, seeded_manager: AccountManager):
        bs = seeded_manager.gen_balance_sheet()
        assert bs["balanced"] is True
        assert len(bs["assets"]) > 0
        assert len(bs["liabilities"]) > 0
        assert len(bs["equity"]) > 0

    def test_account_summary(self, seeded_manager: AccountManager):
        summary = seeded_manager.gen_account_summary()
        assert summary["balanced"] is True
        assert summary["net_worth"] >= 0
        assert len(summary["groups"]) == 5  # Asset, Liability, Equity, Income, Expense

    # ── Balance sheet with live income (pre-close) ────────────

    def test_balance_sheet_balanced_with_live_income(self, seeded_manager: AccountManager):
        """Pre-close: net income appears in equity and balance sheet balances."""
        ids = seeded_manager.account_ids
        # Add income & expense transactions without closing
        seeded_manager.add_transaction(
            datetime(2026, 6, 1), "Paycheck",
            [Split(ids["HS Checking"], 300000), Split(ids.get("Wages", 4), -300000)],
        )
        seeded_manager.add_transaction(
            datetime(2026, 6, 2), "Groceries",
            [Split(ids.get("Groceries", 5), 5000), Split(ids["HS Checking"], -5000)],
        )
        seeded_manager.generate_ledger()

        bs = seeded_manager.gen_balance_sheet()
        assert bs["balanced"] is True, (
            f"Balance sheet must balance with live income. "
            f"A={bs['total_assets']} L={bs['total_liabilities']} E={bs['total_equity']}"
        )
        # Equity should include a net income entry
        equity_names = [n for n, _ in bs["equity"]]
        assert any("net income" in n.lower() for n in equity_names), (
            f"Expected 'net income' in equity, got {equity_names}"
        )

    # ── RE statement doesn't double-count post-close ─────────

    def test_re_statement_no_double_count_after_close(self, seeded_manager: AccountManager):
        """Post-close: RE statement should not inflate by adding NI twice.

        After close_temps(), income/expense are zeroed and NI is in RE.
        The RE statement must detect this and set NI = 0.
        """
        re_before = -seeded_manager.accounts[6].get_balance()

        seeded_manager.close_temps()
        seeded_manager.generate_ledger()

        re_after = -seeded_manager.accounts[6].get_balance()
        re_stmt = seeded_manager.gen_retained_earnings_statement()

        # RE ending from statement should not exceed actual ledger RE
        assert re_stmt["ending_re"] <= re_after, (
            f"RE statement ending ({re_stmt['ending_re']}) exceeds "
            f"actual ledger RE ({re_after})"
        )
        # NI should be zero since income accounts are closed
        assert re_stmt["net_income"] == 0, (
            f"Expected NI=0 post-close, got {re_stmt['net_income']}"
        )

    def test_re_statement_normal_before_close(self, seeded_manager: AccountManager):
        """Pre-close: RE statement reports NI normally."""
        # Add some income first
        ids = seeded_manager.account_ids
        seeded_manager.add_transaction(
            datetime(2026, 6, 1), "Paycheck",
            [Split(ids["HS Checking"], 300000), Split(ids.get("Wages", 4), -300000)],
        )
        seeded_manager.generate_ledger()

        re_stmt = seeded_manager.gen_retained_earnings_statement()
        # NI should be non-zero since income accounts are live
        assert re_stmt["net_income"] > 0, (
            f"Expected NI > 0 pre-close, got {re_stmt['net_income']}"
        )
        ending = re_stmt["beginning_re"] + re_stmt["net_income"] - re_stmt["dividends"]
        assert ending == re_stmt["ending_re"], (
            f"RE equation doesn't hold: {re_stmt['beginning_re']} + "
            f"{re_stmt['net_income']} - {re_stmt['dividends']} != {re_stmt['ending_re']}"
        )

    # ── Balance sheet shows non-leaf accounts with direct balances ──

    def test_balance_sheet_shows_non_leaf_direct_balance(self, seeded_manager: AccountManager):
        """Accounts in the middle of the tree appear if they have direct splits.

        Generate a transaction against 'cash' (a parent of checking/savings)
        and verify it shows up on the balance sheet.
        """
        ids = seeded_manager.account_ids
        # Cash is id=7 (under Assets, may have children in some trees)
        # Add a direct transaction to cash
        cash_id = 7  # parent of checking/savings
        seeded_manager.add_transaction(
            datetime(2026, 6, 1), "Cash deposit",
            [Split(cash_id, 50000), Split(ids["HS Checking"], -50000)],
        )
        seeded_manager.generate_ledger()

        bs = seeded_manager.gen_balance_sheet()
        asset_names = [n for n, _ in bs["assets"]]
        assert "cash" in [n.lower() for n in asset_names], (
            f"Expected 'cash' (non-leaf) on balance sheet, got {asset_names}"
        )
        assert bs["balanced"] is True, (
            f"Balance sheet must still balance with direct non-leaf txn. "
            f"A={bs['total_assets']} L+E={bs['total_liabilities_equity']}"
        )

    # ── Full cycle: pre-close balances → close → post-close balances ──

    def test_balance_sheet_full_cycle(self, seeded_manager: AccountManager):
        """Balance sheet balances before close, after close, and RE doesn't inflate."""
        ids = seeded_manager.account_ids

        # Add income
        seeded_manager.add_transaction(
            datetime(2026, 6, 1), "Paycheck",
            [Split(ids["HS Checking"], 300000), Split(ids.get("Wages", 4), -300000)],
        )
        seeded_manager.add_transaction(
            datetime(2026, 6, 2), "Rent",
            [Split(ids.get("Rent", 5), 150000), Split(ids["HS Checking"], -150000)],
        )
        seeded_manager.generate_ledger()

        # Pre-close: balanced with NI in equity
        bs_pre = seeded_manager.gen_balance_sheet()
        assert bs_pre["balanced"], f"Pre-close unbalanced: {bs_pre}"

        re_pre = seeded_manager.gen_retained_earnings_statement()
        assert re_pre["net_income"] > 0, "Pre-close NI should be positive"

        # Close
        seeded_manager.close_temps()
        seeded_manager.generate_ledger()

        bs_post = seeded_manager.gen_balance_sheet()
        assert bs_post["balanced"], \
            f"Post-close unbalanced: A={bs_post['total_assets']} L+E={bs_post['total_liabilities_equity']}"

        re_post = seeded_manager.gen_retained_earnings_statement()
        assert re_post["net_income"] == 0, \
            f"Post-close NI should be 0, got {re_post['net_income']}"

        # Close AGAIN — should be a no-op
        re_before_2nd_close = -seeded_manager.accounts[6].get_balance()
        seeded_manager.close_temps()
        seeded_manager.generate_ledger()
        re_after_2nd_close = -seeded_manager.accounts[6].get_balance()
        assert re_after_2nd_close == re_before_2nd_close, \
            f"Second close changed RE: {re_before_2nd_close} → {re_after_2nd_close}"
