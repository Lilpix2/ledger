"""Unit tests: budget planning and budget-vs-actual reporting.

All tests use ``fast_manager`` (MockDB, zero disk I/O).
AAA pattern enforced throughout.
"""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


# ═══════════════════════════════════════════════════════════════════
#  Budget CRUD
# ═══════════════════════════════════════════════════════════════════


class TestBudgetCRUD:
    """Creating, reading, updating, deleting budgets."""

    def test_set_budget_creates_entry(self, fast_manager: AccountManager):
        """Arrange: expense account. Act: set budget for June. Assert: stored."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)

        # Act
        fast_manager.set_budget(groceries, "2026-06", 60000)

        # Assert
        assert fast_manager.get_budget(groceries, "2026-06") == 60000

    def test_set_budget_multiple_accounts(self, fast_manager: AccountManager):
        """Arrange: two accounts. Act: set budgets. Assert: both stored independently."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)
        dining = fast_manager.add_account("Dining", 5)

        # Act
        fast_manager.set_budget(groceries, "2026-06", 60000)
        fast_manager.set_budget(dining, "2026-06", 30000)

        # Assert
        assert fast_manager.get_budget(groceries, "2026-06") == 60000
        assert fast_manager.get_budget(dining, "2026-06") == 30000

    def test_set_budget_updates_existing(self, fast_manager: AccountManager):
        """Act: set budget twice. Assert: second value overwrites."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)
        fast_manager.set_budget(groceries, "2026-06", 60000)

        # Act
        fast_manager.set_budget(groceries, "2026-06", 75000)

        # Assert
        assert fast_manager.get_budget(groceries, "2026-06") == 75000

    def test_get_budget_nonexistent_returns_none(self, fast_manager: AccountManager):
        """Arrange: no budget. Act: get_budget. Assert: None."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)

        # Act & Assert
        assert fast_manager.get_budget(groceries, "2026-06") is None

    def test_get_budget_wrong_month_returns_none(self, fast_manager: AccountManager):
        """Arrange: budget for June. Act: query May. Assert: None."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)
        fast_manager.set_budget(groceries, "2026-06", 60000)

        # Act & Assert
        assert fast_manager.get_budget(groceries, "2026-05") is None

    def test_set_budget_multiple_months(self, fast_manager: AccountManager):
        """Act: budgets for different months. Assert: each month's value correct."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)

        # Act
        fast_manager.set_budget(groceries, "2026-06", 60000)
        fast_manager.set_budget(groceries, "2026-07", 65000)

        # Assert
        assert fast_manager.get_budget(groceries, "2026-06") == 60000
        assert fast_manager.get_budget(groceries, "2026-07") == 65000

    def test_set_budget_income_account(self, fast_manager: AccountManager):
        """Budgets work on income accounts too (for savings goals)."""
        # Arrange
        wages = fast_manager.add_account("Wages", 4)

        # Act
        fast_manager.set_budget(wages, "2026-06", 300000)

        # Assert
        assert fast_manager.get_budget(wages, "2026-06") == 300000

    def test_set_budget_zero_amount(self, fast_manager: AccountManager):
        """A budget of zero is valid (planning to spend nothing)."""
        # Arrange
        gambling = fast_manager.add_account("Gambling", 5)

        # Act
        fast_manager.set_budget(gambling, "2026-06", 0)

        # Assert
        assert fast_manager.get_budget(gambling, "2026-06") == 0

    def test_get_budgets_all_for_month(self, fast_manager: AccountManager):
        """get_budgets returns all budget entries for a given month."""
        # Arrange
        a = fast_manager.add_account("A", 5)
        b = fast_manager.add_account("B", 5)
        fast_manager.set_budget(a, "2026-06", 100)
        fast_manager.set_budget(b, "2026-06", 200)
        fast_manager.set_budget(a, "2026-07", 300)

        # Act
        june_budgets = fast_manager.get_budgets("2026-06")

        # Assert
        assert len(june_budgets) == 2
        budgets_by_aid = {aid: amt for aid, mnth, amt in june_budgets}
        assert budgets_by_aid[a] == 100
        assert budgets_by_aid[b] == 200

    def test_get_budgets_no_month_returns_all(self, fast_manager: AccountManager):
        """get_budgets without month filter returns everything."""
        # Arrange
        a = fast_manager.add_account("A", 5)
        b = fast_manager.add_account("B", 5)
        fast_manager.set_budget(a, "2026-06", 100)
        fast_manager.set_budget(b, "2026-07", 200)

        # Act
        all_budgets = fast_manager.get_budgets()

        # Assert
        assert len(all_budgets) == 2

    def test_clear_budget_removes_one(self, fast_manager: AccountManager):
        """clear_budget removes a single budget entry."""
        # Arrange
        a = fast_manager.add_account("A", 5)
        b = fast_manager.add_account("B", 5)
        fast_manager.set_budget(a, "2026-06", 100)
        fast_manager.set_budget(b, "2026-06", 200)

        # Act
        fast_manager.clear_budget(a, "2026-06")

        # Assert
        assert fast_manager.get_budget(a, "2026-06") is None
        assert fast_manager.get_budget(b, "2026-06") == 200

    def test_clear_budget_nonexistent_does_nothing(self, fast_manager: AccountManager):
        """Clearing a budget that doesn't exist doesn't raise."""
        # Arrange & Act
        fast_manager.clear_budget(999, "2026-06")
        # Assert — no exception raised

    def test_clear_all_budgets_for_month(self, fast_manager: AccountManager):
        """clear_all_budgets removes all budgets for a month."""
        # Arrange
        a = fast_manager.add_account("A", 5)
        b = fast_manager.add_account("B", 5)
        fast_manager.set_budget(a, "2026-06", 100)
        fast_manager.set_budget(b, "2026-06", 200)
        fast_manager.set_budget(a, "2026-07", 300)

        # Act
        fast_manager.clear_all_budgets("2026-06")

        # Assert
        assert fast_manager.get_budget(a, "2026-06") is None
        assert fast_manager.get_budget(b, "2026-06") is None
        assert fast_manager.get_budget(a, "2026-07") == 300  # July untouched


# ═══════════════════════════════════════════════════════════════════
#  Budget vs Actual
# ═══════════════════════════════════════════════════════════════════


class TestBudgetVsActual:
    """Budget-vs-actual comparison calculations."""

    def _setup(self, mgr: AccountManager):
        """Helper: create accounts with budgets and transactions."""
        groceries = mgr.add_account("Groceries", 5)
        dining = mgr.add_account("Dining", 5)
        rent = mgr.add_account("Rent", 5)
        checking = mgr.add_account("Checking", 1)
        wages = mgr.add_account("Wages", 4)

        # Set budgets for June
        mgr.set_budget(groceries, "2026-06", 60000)
        mgr.set_budget(dining, "2026-06", 30000)
        mgr.set_budget(rent, "2026-06", 150000)

        # Fund checking
        mgr.add_transaction(datetime(2026, 1, 1), "Fund", [
            Split(checking, 500000), Split(6, -500000),
        ])

        # June transactions
        mgr.add_transaction(datetime(2026, 6, 5), "Rent", [
            Split(rent, 150000), Split(checking, -150000),
        ])
        mgr.add_transaction(datetime(2026, 6, 7), "Sprouts", [
            Split(groceries, 8500), Split(checking, -8500),
        ])
        mgr.add_transaction(datetime(2026, 6, 10), "Costco", [
            Split(groceries, 12000), Split(checking, -12000),
        ])
        mgr.add_transaction(datetime(2026, 6, 15), "Chipotle", [
            Split(dining, 1800), Split(checking, -1800),
        ])
        mgr.generate_ledger()

        return {
            "groceries": groceries,
            "dining": dining,
            "rent": rent,
            "wages": wages,
        }

    def test_budget_vs_actual_returns_comparisons(self, fast_manager: AccountManager):
        """budget_vs_actual returns entries for budgeted accounts."""
        # Arrange
        ids = self._setup(fast_manager)

        # Act
        results = fast_manager.budget_vs_actual("2026-06")

        # Assert
        # Only budgeted accounts appear (groceries, dining, rent)
        assert len(results) == 3

        result_by_name = {r["name"]: r for r in results}
        assert "Groceries" in result_by_name
        assert "Dining" in result_by_name
        assert "Rent" in result_by_name

    def test_budget_vs_actual_correct_amounts(self, fast_manager: AccountManager):
        """Calculated budget, actual, remaining are correct."""
        # Arrange
        ids = self._setup(fast_manager)

        # Act
        results = fast_manager.budget_vs_actual("2026-06")
        result_by_name = {r["name"]: r for r in results}

        # Groceries: budget 60000, actual 8500+12000=20500, remaining 39500
        g = result_by_name["Groceries"]
        assert g["budget"] == 60000
        assert g["actual"] == 20500
        assert g["remaining"] == 39500
        assert g["pct_used"] == pytest.approx(34.17, rel=0.01)

        # Dining: budget 30000, actual 1800, remaining 28200
        d = result_by_name["Dining"]
        assert d["budget"] == 30000
        assert d["actual"] == 1800
        assert d["remaining"] == 28200
        assert d["pct_used"] == pytest.approx(6.0, rel=0.01)

        # Rent: budget 150000, actual 150000, remaining 0, 100%
        r = result_by_name["Rent"]
        assert r["budget"] == 150000
        assert r["actual"] == 150000
        assert r["remaining"] == 0
        assert r["pct_used"] == 100.0

    def test_budget_vs_actual_over_budget_shows_negative_remaining(
        self, fast_manager: AccountManager,
    ):
        """Spending more than budget → remaining is negative."""
        # Arrange
        dining = fast_manager.add_account("Dining", 5)
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.set_budget(dining, "2026-06", 10000)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Fund", [
            Split(checking, 100000), Split(6, -100000),
        ])
        fast_manager.add_transaction(datetime(2026, 6, 1), "UberEats", [
            Split(dining, 15000), Split(checking, -15000),
        ])
        fast_manager.add_transaction(datetime(2026, 6, 2), "DoorDash", [
            Split(dining, 5000), Split(checking, -5000),
        ])
        fast_manager.generate_ledger()

        # Act
        results = fast_manager.budget_vs_actual("2026-06")

        # Assert
        d = results[0]
        assert d["budget"] == 10000
        assert d["actual"] == 20000
        assert d["remaining"] == -10000
        assert d["pct_used"] == 200.0

    def test_budget_vs_actual_no_spending(self, fast_manager: AccountManager):
        """Budget with zero spending → 0% used."""
        # Arrange
        groceries = fast_manager.add_account("Groceries", 5)
        fast_manager.set_budget(groceries, "2026-06", 60000)

        # Act
        results = fast_manager.budget_vs_actual("2026-06")

        # Assert
        g = results[0]
        assert g["budget"] == 60000
        assert g["actual"] == 0
        assert g["remaining"] == 60000
        assert g["pct_used"] == 0.0

    def test_budget_vs_actual_no_budgets_returns_empty(
        self, fast_manager: AccountManager,
    ):
        """No budgets set → empty list."""
        # Arrange
        fast_manager.add_account("Groceries", 5)

        # Act & Assert
        assert fast_manager.budget_vs_actual("2026-06") == []

    def test_budget_vs_actual_zero_budget_with_spending(
        self, fast_manager: AccountManager,
    ):
        """Budget of $0 with actual spending → inf pct_used or very large."""
        # Arrange
        gambling = fast_manager.add_account("Gambling", 5)
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.set_budget(gambling, "2026-06", 0)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Fund", [
            Split(checking, 100000), Split(6, -100000),
        ])
        fast_manager.add_transaction(datetime(2026, 6, 1), "VGW", [
            Split(gambling, 5000), Split(checking, -5000),
        ])
        fast_manager.generate_ledger()

        # Act
        results = fast_manager.budget_vs_actual("2026-06")

        # Assert — should handle zero-budget gracefully
        g = results[0]
        assert g["budget"] == 0
        assert g["actual"] == 5000
        assert g["remaining"] == -5000

    def test_budget_vs_actual_sums_child_accounts(
        self, fast_manager: AccountManager,
    ):
        """Budget on a parent account sums actual from all children."""
        # Arrange
        food = fast_manager.add_account("Food", 5)  # parent expense
        groceries = fast_manager.add_account("Groceries", food)
        dining = fast_manager.add_account("Dining", food)
        checking = fast_manager.add_account("Checking", 1)

        # Budget the parent
        fast_manager.set_budget(food, "2026-06", 100000)

        fast_manager.add_transaction(datetime(2026, 1, 1), "Fund", [
            Split(checking, 200000), Split(6, -200000),
        ])
        fast_manager.add_transaction(datetime(2026, 6, 5), "Sprouts", [
            Split(groceries, 30000), Split(checking, -30000),
        ])
        fast_manager.add_transaction(datetime(2026, 6, 10), "Chipotle", [
            Split(dining, 15000), Split(checking, -15000),
        ])
        fast_manager.generate_ledger()

        # Act
        results = fast_manager.budget_vs_actual("2026-06")

        # Assert
        f = results[0]
        assert f["budget"] == 100000
        assert f["actual"] == 45000  # 30000 + 15000
        assert f["remaining"] == 55000
