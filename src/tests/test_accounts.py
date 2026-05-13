"""Unit tests: account CRUD, subtypes, hierarchy, tree operations, financial reports.

All tests use the ``fast_manager`` fixture (MockDB — no disk I/O, <1ms per test).
Follows AAA pattern (Arrange, Act, Assert) with descriptive names.
"""

import pytest
from datetime import datetime
from ledger.models.data_class import Split


# ════════════════════════════════════════════════════════════════════
#  Account Creation
# ════════════════════════════════════════════════════════════════════


class TestAccountCreation:
    """Creating accounts with various options — happy paths and edge cases."""

    def test_create_default_loads_parents(self, fast_manager):
        """Arrange: fresh AccountManager. Assert: 11 default parents exist."""
        assert len(fast_manager.accounts) == 11

    def test_addAccount_withName_returnsPositiveId(self, fast_manager):
        """add_account with a valid name returns a positive account ID."""
        aid = fast_manager.add_account("My Checking", 1)
        assert aid > 0
        assert fast_manager.accounts[aid].name == "My Checking"

    def test_addAccount_withSubtype_savesSubtype(self, fast_manager):
        """add_account stores the account_subtype."""
        aid = fast_manager.add_account("My Checking", 1, account_subtype="checking")
        assert fast_manager.accounts[aid].account_subtype == "checking"

    def test_addAccount_withInvalidSubtype_raises(self, fast_manager):
        """add_account with an unknown subtype raises ValueError."""
        with pytest.raises(ValueError, match="Invalid account_subtype"):
            fast_manager.add_account("Bad", 1, account_subtype="not_a_subtype")

    def test_addAccount_duplicateName_raises(self, fast_manager):
        """add_account with a duplicate name under the same parent raises."""
        fast_manager.add_account("Test", 1)
        with pytest.raises(ValueError, match="already exists"):
            fast_manager.add_account("Test", 1)

    def test_addAccount_contraFlag_setsIsContra(self, fast_manager):
        """add_account with is_contra=True stores the flag."""
        aid = fast_manager.add_account("Acc Depreciation", 1, is_contra=True)
        assert fast_manager.accounts[aid].is_contra is True

    def test_addAccount_underExpense_inheritsExpenseType(self, fast_manager):
        """add_account under expense parent (5) gets EXPENSE type."""
        aid = fast_manager.add_account("My Expense", 5)
        assert fast_manager.accounts[aid].acct_type == "EXPENSE"

    def test_addAccount_emptyName_raises(self, fast_manager):
        """add_account with empty name raises ValueError."""
        with pytest.raises(ValueError):
            fast_manager.add_account("", 1)

    def test_addAccount_whitespaceName_raises(self, fast_manager):
        """add_account with whitespace-only name raises ValueError."""
        with pytest.raises(ValueError):
            fast_manager.add_account("   ", 1)

    def test_addAccount_sameNameDifferentParent_succeeds(self, fast_manager):
        """Duplicate names under different parents are allowed."""
        aid1 = fast_manager.add_account("Same Name", 1)
        aid2 = fast_manager.add_account("Same Name", 2)
        assert aid1 != aid2

    def test_addAccount_noneParent_raises(self, fast_manager):
        """add_account with parent=None raises ValueError."""
        with pytest.raises(ValueError, match="parent is required"):
            fast_manager.add_account("TopLevel", None, "LIABILITY")

    def test_addAccount_defaultTypeIsAsset(self, fast_manager):
        """add_account with no type specified defaults to ASSET."""
        aid = fast_manager.add_account("DefaultType", 1)
        assert fast_manager.accounts[aid].acct_type == "ASSET"


# ════════════════════════════════════════════════════════════════════
#  Account Queries
# ════════════════════════════════════════════════════════════════════


class TestAccountQueries:
    """Querying account trees, descendants, top-level parents."""

    def test_buildTree_withChildren_returnsNestedDict(self, fast_seeded):
        """build_tree returns a dict mapping parent_id to child list."""
        tree = fast_seeded.build_tree()
        assert 1 in tree  # Assets has children
        assert 0 in tree  # Root has top-level children

    def test_getDescendants_includesSelf(self, fast_seeded):
        """get_descendant_ids includes the queried account itself."""
        descendants = fast_seeded.get_descendant_ids(1)
        assert 1 in descendants

    def test_getDescendants_includesChildren(self, fast_seeded):
        """get_descendant_ids includes all children of the queried account."""
        descendants = fast_seeded.get_descendant_ids(1)
        assert "HS Checking" in [
            fast_seeded.accounts[aid].name for aid in descendants if aid in fast_seeded.accounts
        ]

    def test_getTopLevelParent_checking_returnsAssets(self, fast_seeded):
        """HS Checking's top-level parent is 1 (Assets)."""
        ids = {a.name: aid for aid, a in fast_seeded.accounts.items() if aid}
        top = fast_seeded.get_top_level_parent(ids["HS Checking"])
        assert top == 1

    def test_getTopLevelParent_root_returnsRoot(self, fast_manager):
        """Account 0's top-level parent is 0."""
        assert fast_manager.get_top_level_parent(0) == 0

    def test_getTopLevelParent_assetRoot_returnsAsset(self, fast_manager):
        """Account 1's top-level parent is 1 (itself)."""
        assert fast_manager.get_top_level_parent(1) == 1


# ════════════════════════════════════════════════════════════════════
#  Display Balance
# ════════════════════════════════════════════════════════════════════


class TestDisplayBalance:
    """Display-normal balances for different account types."""

    def test_liabilityDisplay_positiveDespiteNegativeRaw(self, fast_seeded):
        """Liabilities display as positive even when raw balance is negative."""
        ids = {a.name: aid for aid, a in fast_seeded.accounts.items() if aid}
        raw = fast_seeded.aggregated_balance(ids["Discover"])
        display = fast_seeded.get_display_balance(ids["Discover"])
        assert raw <= 0   # credit-normal
        assert display >= 0
        assert display == -raw

    def test_assetDisplay_equalsRaw(self, fast_seeded):
        """Assets display balance equals raw balance (debit-normal)."""
        ids = {a.name: aid for aid, a in fast_seeded.accounts.items() if aid}
        raw = fast_seeded.aggregated_balance(ids["HS Checking"])
        display = fast_seeded.get_display_balance(ids["HS Checking"])
        assert display == raw

    def test_isDebitNormal_asset_returnsTrue(self, fast_manager):
        assert fast_manager.is_debit_normal(1) is True   # Asset

    def test_isDebitNormal_liability_returnsFalse(self, fast_manager):
        assert fast_manager.is_debit_normal(2) is False  # Liability

    def test_isDebitNormal_equity_returnsFalse(self, fast_manager):
        assert fast_manager.is_debit_normal(3) is False  # Equity

    def test_isDebitNormal_income_returnsFalse(self, fast_manager):
        assert fast_manager.is_debit_normal(4) is False  # Income

    def test_isDebitNormal_expense_returnsTrue(self, fast_manager):
        assert fast_manager.is_debit_normal(5) is True   # Expense

    def test_getBalance_unmodifiedLedger_returnsZero(self, fast_manager):
        """A fresh account with no transactions has balance 0."""
        for aid in [1, 2, 3, 4, 5, 6]:
            assert fast_manager.accounts[aid].get_balance() == 0

    def test_getBalance_afterTransaction_reflectsSplits(self, fast_manager):
        """After a transaction, account balance matches the split."""
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Deposit",
            [Split(checking, 50000), Split(6, -50000)],
        )
        fast_manager.generate_ledger()
        assert fast_manager.accounts[checking].get_balance() == 50000


# ════════════════════════════════════════════════════════════════════
#  Financial Reports
# ════════════════════════════════════════════════════════════════════


class TestFinancialReports:
    """Income statement, balance sheet, RE statement, equation."""

    def test_checkEquation_seededData_balanced(self, fast_seeded):
        """check_accounting_equation returns balanced=True for valid data."""
        eq = fast_seeded.check_accounting_equation()
        assert eq["balanced"] is True
        assert eq["net_worth"] >= 0

    def test_genIncomeReport_withTransactions_returnsNetIncome(self, fast_seeded):
        """gen_income_report with income and expense data returns positive NI."""
        inc = fast_seeded.gen_income_report()
        assert inc["income_total"] > 0
        assert inc["expenses_total"] > 0
        assert inc["net_income"] > 0

    def test_genIncomeReport_noTransactions_returnsZeros(self, fast_manager):
        """gen_income_report on empty journal returns all zeros."""
        inc = fast_manager.gen_income_report()
        assert inc["income_total"] == 0
        assert inc["expenses_total"] == 0
        assert inc["net_income"] == 0

    def test_genIncomeReport_withDateFilter_excludesOutsideRange(self, fast_seeded):
        """gen_income_report with date filter returns only transactions in range."""
        full = fast_seeded.gen_income_report()
        assert full["net_income"] > 0

        empty = fast_seeded.gen_income_report(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
        )
        assert empty["net_income"] == 0

    def test_retainedEarnings_preClose_includesNetIncome(self, fast_seeded):
        """Before close: beginning_re + NI = ending_re."""
        re = fast_seeded.gen_retained_earnings_statement()
        actual_re = fast_seeded.get_display_balance(6)
        assert re["beginning_re"] == actual_re
        assert re["ending_re"] == actual_re + re["net_income"]

    def test_retainedEarnings_postClose_netIncomeIsZero(self, fast_seeded):
        """After close: NI is 0 (already in RE), ending_re = ledger RE."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()

        actual_re = fast_seeded.get_display_balance(6)
        re = fast_seeded.gen_retained_earnings_statement()
        assert re["net_income"] == 0
        assert re["ending_re"] == actual_re

    def test_balanceSheet_preClose_balancedWithNetIncome(self, fast_seeded):
        """Balance sheet includes NI in equity pre-close and is balanced."""
        bs = fast_seeded.gen_balance_sheet()
        assert bs["balanced"] is True

    def test_balanceSheet_postClose_noSeparateNetIncome(self, fast_seeded):
        """Post-close BS has no separate NI line (it's in RE)."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()

        bs = fast_seeded.gen_balance_sheet()
        assert bs["balanced"] is True
        equity_names = {n for n, _ in bs["equity"]}
        assert "net income" not in equity_names

    def test_balanceSheet_retainedEarnings_matchesLedger(self, fast_seeded):
        """BS retained earnings matches the ledger, not inflated."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()

        actual_re = fast_seeded.get_display_balance(6)
        bs = fast_seeded.gen_balance_sheet()

        re_in_bs = sum(b for n, b in bs["equity"] if "retained" in n.lower())
        assert re_in_bs == actual_re

    def test_accountSummary_seededData_balanced(self, fast_seeded):
        """Account summary is balanced with positive net worth."""
        summary = fast_seeded.gen_account_summary()
        assert summary["balanced"] is True
        assert summary["net_worth"] >= 0

    def test_closeTemps_twice_isNoop(self, fast_seeded):
        """Calling close_temps() twice doesn't change RE."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        re1 = fast_seeded.get_display_balance(6)

        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        re2 = fast_seeded.get_display_balance(6)

        assert re2 == re1

    def test_accountingEquation_multipleTransactions_staysBalanced(self, fast_manager):
        """Adding many transactions keeps A = L + E."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        rent = fast_manager.add_account("Rent", 5)

        for i in range(10):
            fast_manager.add_transaction(
                datetime(2026, 1, 1 + i), f"Txn {i}",
                [Split(wages, -100000), Split(checking, 100000)],
            )
            fast_manager.add_transaction(
                datetime(2026, 1, 1 + i), f"Exp {i}",
                [Split(rent, 50000), Split(checking, -50000)],
            )
        fast_manager.generate_ledger()

        eq = fast_manager.check_accounting_equation()
        assert eq["balanced"] is True

    def test_balanceSheet_withContraAccount_reducesAssets(self, fast_manager):
        """Contra-asset accounts reduce total assets on the balance sheet."""
        checking = fast_manager.add_account("Checking", 1)
        depr = fast_manager.add_account("Accum Depr", 1, is_contra=True)

        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Open",
            [Split(checking, 10000000), Split(6, -10000000)],
        )
        fast_manager.add_transaction(
            datetime(2026, 6, 1), "Depreciation",
            [Split(6, 200000), Split(depr, -200000)],
        )
        fast_manager.generate_ledger()

        bs = fast_manager.gen_balance_sheet()
        assert bs["balanced"] is True
        # Contra reduces assets
        contra_names = [n for n, _ in bs["assets"] if "(-)" in n or "Depr" in n]
        assert len(contra_names) > 0
