"""Unit tests: account CRUD, subtypes, hierarchy, and tree operations."""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager


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
