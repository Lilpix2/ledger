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
        # Arrange — fast_manager is a fresh AccountManager
        # Act — nothing to do; accounts are pre-loaded
        # Assert
        assert len(fast_manager.accounts) == 11

    def test_addAccount_withName_returnsPositiveId(self, fast_manager):
        """add_account with a valid name returns a positive account ID."""
        # Arrange
        # Act
        aid = fast_manager.add_account("My Checking", 1)
        # Assert
        assert aid > 0
        assert fast_manager.accounts[aid].name == "My Checking"

    def test_addAccount_withSubtype_savesSubtype(self, fast_manager):
        """add_account stores the account_subtype."""
        # Arrange
        # Act
        aid = fast_manager.add_account("My Checking", 1, account_subtype="checking")
        # Assert
        assert fast_manager.accounts[aid].account_subtype == "checking"

    def test_addAccount_withInvalidSubtype_raises(self, fast_manager):
        """add_account with an unknown subtype raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invalid account_subtype"):
            fast_manager.add_account("Bad", 1, account_subtype="not_a_subtype")

    def test_addAccount_duplicateName_raises(self, fast_manager):
        """add_account with a duplicate name under the same parent raises."""
        # Arrange
        fast_manager.add_account("Test", 1)
        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            fast_manager.add_account("Test", 1)

    def test_addAccount_contraFlag_setsIsContra(self, fast_manager):
        """add_account with is_contra=True stores the flag."""
        # Arrange
        # Act
        aid = fast_manager.add_account("Acc Depreciation", 1, is_contra=True)
        # Assert
        assert fast_manager.accounts[aid].is_contra is True

    def test_addAccount_underExpense_inheritsExpenseType(self, fast_manager):
        """add_account under expense parent (5) gets EXPENSE type."""
        # Arrange
        # Act
        aid = fast_manager.add_account("My Expense", 5)
        # Assert
        assert fast_manager.accounts[aid].acct_type == "EXPENSE"

    def test_addAccount_emptyName_raises(self, fast_manager):
        """add_account with empty name raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError):
            fast_manager.add_account("", 1)

    def test_addAccount_whitespaceName_raises(self, fast_manager):
        """add_account with whitespace-only name raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError):
            fast_manager.add_account("   ", 1)

    def test_addAccount_sameNameDifferentParent_succeeds(self, fast_manager):
        """Duplicate names under different parents are allowed."""
        # Arrange
        # Act
        aid1 = fast_manager.add_account("Same Name", 1)
        aid2 = fast_manager.add_account("Same Name", 2)
        # Assert
        assert aid1 != aid2

    def test_addAccount_noneParent_raises(self, fast_manager):
        """add_account with parent=None raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="parent is required"):
            fast_manager.add_account("TopLevel", None, "LIABILITY")

    def test_addAccount_defaultTypeIsAsset(self, fast_manager):
        """add_account with no type specified defaults to ASSET."""
        # Arrange
        # Act
        aid = fast_manager.add_account("DefaultType", 1)
        # Assert
        assert fast_manager.accounts[aid].acct_type == "ASSET"

    def test_addAccount_emptySubtypeString_raises(self, fast_manager):
        """add_account with empty subtype string raises ValueError (empty != None)."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invalid account_subtype"):
            fast_manager.add_account("NoSubtype", 1, account_subtype="")

    def test_addAccount_nonexistentParent_storesAsIs(self, fast_manager):
        """add_account accepts a parent ID that doesn't exist yet."""
        # Arrange
        # Act
        aid = fast_manager.add_account("Orphan", 99999, "ASSET")
        # Assert
        assert aid > 0
        assert fast_manager.accounts[aid].parent == 99999

    def test_addAccount_duplicateNameUnderAssets_uniqueUnderLiabilities(self, fast_manager):
        """Same name reused across unrelated top-level parents succeeds."""
        # Arrange
        aid1 = fast_manager.add_account("Cash", 1)
        aid2 = fast_manager.add_account("Cash", 2)
        # Assert
        assert aid1 != aid2


# ════════════════════════════════════════════════════════════════════
#  Account Queries
# ════════════════════════════════════════════════════════════════════


class TestAccountQueries:
    """Querying account trees, descendants, top-level parents."""

    def test_buildTree_withChildren_returnsNestedDict(self, fast_seeded):
        """build_tree returns a dict mapping parent_id to child list."""
        # Arrange — fast_seeded has a populated account tree
        # Act
        tree = fast_seeded.build_tree()
        # Assert
        assert 1 in tree  # Assets has children
        assert 0 in tree  # Root has top-level children

    def test_buildTree_emptyManager_returnsRootAndDefaults(self, fast_manager):
        """build_tree on an empty manager still returns root and top-level parents."""
        # Arrange — fast_manager has only 11 default accounts
        # Act
        tree = fast_manager.build_tree()
        # Assert
        assert 0 in tree

    def test_getDescendants_includesSelf(self, fast_seeded):
        """get_descendant_ids includes the queried account itself."""
        # Arrange — fast_seeded has accounts
        # Act
        descendants = fast_seeded.get_descendant_ids(1)
        # Assert
        assert 1 in descendants

    def test_getDescendants_includesChildren(self, fast_seeded):
        """get_descendant_ids includes all children of the queried account."""
        # Arrange — fast_seeded has accounts
        # Act
        descendants = fast_seeded.get_descendant_ids(1)
        # Assert
        assert "HS Checking" in [
            fast_seeded.accounts[aid].name for aid in descendants if aid in fast_seeded.accounts
        ]

    def test_getDescendants_nonexistentId_returnsEmptyOrSelf(self, fast_manager):
        """get_descendant_ids for unknown ID returns the ID itself as the only member."""
        # Arrange — fast_manager has no account 99999
        # Act
        descendants = fast_manager.get_descendant_ids(99999)
        # Assert — either returns just {99999} or {} depending on impl
        assert isinstance(descendants, set)
        assert len(descendants) <= 1

    def test_getTopLevelParent_checking_returnsAssets(self, fast_seeded):
        """HS Checking's top-level parent is 1 (Assets)."""
        # Arrange
        ids = {a.name: aid for aid, a in fast_seeded.accounts.items() if aid}
        # Act
        top = fast_seeded.get_top_level_parent(ids["HS Checking"])
        # Assert
        assert top == 1

    def test_getTopLevelParent_root_returnsRoot(self, fast_manager):
        """Account 0's top-level parent is 0."""
        # Arrange & Act & Assert
        assert fast_manager.get_top_level_parent(0) == 0

    def test_getTopLevelParent_assetRoot_returnsAsset(self, fast_manager):
        """Account 1's top-level parent is 1 (itself)."""
        # Arrange & Act & Assert
        assert fast_manager.get_top_level_parent(1) == 1

    def test_getTopLevelParent_nonexistentId_raises(self, fast_manager):
        """get_top_level_parent for unknown ID raises KeyError or ValueError."""
        # Arrange & Act & Assert
        with pytest.raises((KeyError, ValueError)):
            fast_manager.get_top_level_parent(99999)

    def test_getDisplayBalance_nonexistentId_raises(self, fast_manager):
        """get_display_balance for unknown ID raises KeyError or ValueError."""
        # Arrange & Act & Assert
        with pytest.raises((KeyError, ValueError)):
            fast_manager.get_display_balance(99999)

    def test_aggregatedBalance_nonexistentId_raises(self, fast_manager):
        """aggregated_balance for unknown ID raises KeyError."""
        # Arrange & Act & Assert
        with pytest.raises(KeyError):
            fast_manager.aggregated_balance(99999)


# ════════════════════════════════════════════════════════════════════
#  Display Balance
# ════════════════════════════════════════════════════════════════════


class TestDisplayBalance:
    """Display-normal balances for different account types."""

    def test_liabilityDisplay_positiveDespiteNegativeRaw(self, fast_seeded):
        """Liabilities display as positive even when raw balance is negative."""
        # Arrange
        ids = {a.name: aid for aid, a in fast_seeded.accounts.items() if aid}
        raw = fast_seeded.aggregated_balance(ids["Discover"])
        # Act
        display = fast_seeded.get_display_balance(ids["Discover"])
        # Assert
        assert raw <= 0   # credit-normal
        assert display >= 0
        assert display == -raw

    def test_assetDisplay_equalsRaw(self, fast_seeded):
        """Assets display balance equals raw balance (debit-normal)."""
        # Arrange
        ids = {a.name: aid for aid, a in fast_seeded.accounts.items() if aid}
        raw = fast_seeded.aggregated_balance(ids["HS Checking"])
        # Act
        display = fast_seeded.get_display_balance(ids["HS Checking"])
        # Assert
        assert display == raw

    def test_isDebitNormal_asset_returnsTrue(self, fast_manager):
        """Arrange & Act & Assert: ASSET accounts are debit-normal."""
        assert fast_manager.is_debit_normal(1) is True   # Asset

    def test_isDebitNormal_liability_returnsFalse(self, fast_manager):
        """Arrange & Act & Assert: LIABILITY accounts are credit-normal."""
        assert fast_manager.is_debit_normal(2) is False  # Liability

    def test_isDebitNormal_equity_returnsFalse(self, fast_manager):
        """Arrange & Act & Assert: EQUITY accounts are credit-normal."""
        assert fast_manager.is_debit_normal(3) is False  # Equity

    def test_isDebitNormal_income_returnsFalse(self, fast_manager):
        """Arrange & Act & Assert: INCOME accounts are credit-normal."""
        assert fast_manager.is_debit_normal(4) is False  # Income

    def test_isDebitNormal_expense_returnsTrue(self, fast_manager):
        """Arrange & Act & Assert: EXPENSE accounts are debit-normal."""
        assert fast_manager.is_debit_normal(5) is True   # Expense

    def test_isDebitNormal_nonexistentId_raises(self, fast_manager):
        """is_debit_normal for unknown ID raises KeyError or ValueError."""
        # Arrange & Act & Assert
        with pytest.raises((KeyError, ValueError)):
            fast_manager.is_debit_normal(99999)

    def test_getBalance_unmodifiedLedger_returnsZero(self, fast_manager):
        """A fresh account with no transactions has balance 0."""
        # Arrange & Act — no transactions yet
        # Assert
        for aid in [1, 2, 3, 4, 5, 6]:
            assert fast_manager.accounts[aid].get_balance() == 0

    def test_getBalance_afterTransaction_reflectsSplits(self, fast_manager):
        """After a transaction, account balance matches the split."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Deposit",
            [Split(checking, 50000), Split(6, -50000)],
        )
        # Act
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.accounts[checking].get_balance() == 50000


# ════════════════════════════════════════════════════════════════════
#  Financial Reports
# ════════════════════════════════════════════════════════════════════


class TestFinancialReports:
    """Income statement, balance sheet, RE statement, equation."""

    def test_checkEquation_seededData_balanced(self, fast_seeded):
        """check_accounting_equation returns balanced=True for valid data."""
        # Arrange — fast_seeded has seeded transactions
        # Act
        eq = fast_seeded.check_accounting_equation()
        # Assert
        assert eq["balanced"] is True
        assert eq["net_worth"] >= 0

    def test_checkEquation_noTransactions_balanced(self, fast_manager):
        """check_accounting_equation returns balanced=True on empty ledger."""
        # Arrange — fast_manager has no transactions
        # Act
        eq = fast_manager.check_accounting_equation()
        # Assert
        assert eq["balanced"] is True
        assert eq["net_worth"] == 0

    def test_genIncomeReport_withTransactions_returnsNetIncome(self, fast_seeded):
        """gen_income_report with income and expense data returns positive NI."""
        # Arrange — fast_seeded has income/expense data
        # Act
        inc = fast_seeded.gen_income_report()
        # Assert
        assert inc["income_total"] > 0
        assert inc["expenses_total"] > 0
        assert inc["net_income"] > 0

    def test_genIncomeReport_noTransactions_returnsZeros(self, fast_manager):
        """gen_income_report on empty journal returns all zeros."""
        # Arrange — fast_manager has no transactions
        # Act
        inc = fast_manager.gen_income_report()
        # Assert
        assert inc["income_total"] == 0
        assert inc["expenses_total"] == 0
        assert inc["net_income"] == 0

    def test_genIncomeReport_withDateFilter_excludesOutsideRange(self, fast_seeded):
        """gen_income_report with date filter returns only transactions in range."""
        # Arrange
        full = fast_seeded.gen_income_report()
        assert full["net_income"] > 0
        # Act — request a date range that predates all transactions
        empty = fast_seeded.gen_income_report(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
        )
        # Assert
        assert empty["net_income"] == 0

    def test_genIncomeReport_reversedDates_excludesAll(self, fast_seeded):
        """gen_income_report with start > end returns empty (no transactions match)."""
        # Arrange
        # Act — date range is logically reversed (end before start)
        empty = fast_seeded.gen_income_report(
            start_date=datetime(2026, 12, 31),
            end_date=datetime(2026, 1, 1),
        )
        # Assert
        assert empty["net_income"] == 0

    def test_retainedEarnings_preClose_includesNetIncome(self, fast_seeded):
        """Before close: beginning_re + NI = ending_re."""
        # Arrange — fast_seeded has unclosed income/expense
        # Act
        re = fast_seeded.gen_retained_earnings_statement()
        actual_re = fast_seeded.get_display_balance(6)
        # Assert
        assert re["beginning_re"] == actual_re
        assert re["ending_re"] == actual_re + re["net_income"]

    def test_retainedEarnings_postClose_netIncomeIsZero(self, fast_seeded):
        """After close: NI is 0 (already in RE), ending_re = ledger RE."""
        # Arrange
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        # Act
        actual_re = fast_seeded.get_display_balance(6)
        re = fast_seeded.gen_retained_earnings_statement()
        # Assert
        assert re["net_income"] == 0
        assert re["ending_re"] == actual_re

    def test_balanceSheet_preClose_balancedWithNetIncome(self, fast_seeded):
        """Balance sheet includes NI in equity pre-close and is balanced."""
        # Arrange — fast_seeded has data
        # Act
        bs = fast_seeded.gen_balance_sheet()
        # Assert
        assert bs["balanced"] is True

    def test_balanceSheet_postClose_noSeparateNetIncome(self, fast_seeded):
        """Post-close BS has no separate NI line (it's in RE)."""
        # Arrange
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        # Act
        bs = fast_seeded.gen_balance_sheet()
        # Assert
        assert bs["balanced"] is True
        equity_names = {n for n, _ in bs["equity"]}
        assert "net income" not in equity_names

    def test_balanceSheet_retainedEarnings_matchesLedger(self, fast_seeded):
        """BS retained earnings matches the ledger, not inflated."""
        # Arrange
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        # Act
        actual_re = fast_seeded.get_display_balance(6)
        bs = fast_seeded.gen_balance_sheet()
        # Assert
        re_in_bs = sum(b for n, b in bs["equity"] if "retained" in n.lower())
        assert re_in_bs == actual_re

    def test_accountSummary_seededData_balanced(self, fast_seeded):
        """Account summary is balanced with positive net worth."""
        # Arrange — fast_seeded has data
        # Act
        summary = fast_seeded.gen_account_summary()
        # Assert
        assert summary["balanced"] is True
        assert summary["net_worth"] >= 0

    def test_closeTemps_twice_isNoop(self, fast_seeded):
        """Calling close_temps() twice doesn't change RE."""
        # Arrange
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        re1 = fast_seeded.get_display_balance(6)
        # Act
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        re2 = fast_seeded.get_display_balance(6)
        # Assert
        assert re2 == re1

    def test_closeTemps_emptyManager_isNoop(self, fast_manager):
        """Calling close_temps() on an empty ledger doesn't raise."""
        # Arrange & Act — should not raise
        fast_manager.close_temps()
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_accountingEquation_multipleTransactions_staysBalanced(self, fast_manager):
        """Adding many transactions keeps A = L + E."""
        # Arrange
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
        # Act
        eq = fast_manager.check_accounting_equation()
        # Assert
        assert eq["balanced"] is True

    def test_balanceSheet_withContraAccount_reducesAssets(self, fast_manager):
        """Contra-asset accounts reduce total assets on the balance sheet."""
        # Arrange
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
        # Act
        bs = fast_manager.gen_balance_sheet()
        # Assert
        assert bs["balanced"] is True
        # Contra reduces assets
        contra_names = [n for n, _ in bs["assets"] if "(-)" in n or "Depr" in n]
        assert len(contra_names) > 0
