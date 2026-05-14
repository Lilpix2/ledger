"""Tests: transaction search and filter functionality.

The search/filter feature allows filtering the journal table by:
  • Description text (case-insensitive substring match)
  • Date range (from / to)
  • Amount range (min / max)

Filters compose with each other and with the existing account-tree filter.
"""

from datetime import datetime
import pytest

from datetime import datetime
import pytest

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from tests.conftest import MockDB


# ── Helper ─────────────────────────────────────────────────────────


def _filter_txns(
    manager: AccountManager,
    search_text: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
) -> list[int]:
    """Return transaction IDs that match all provided filters.

    This mirrors the filtering logic that will live in the GUI's
    ``_refresh_table()`` — kept here as a pure-function test target
    so we don't need tkinter.
    """
    results: list[int] = []

    for txn_id in sorted(manager.journal.transactions.keys()):
        txn = manager.journal.transactions[txn_id]

        # ── Description ──────────────────────────────────────
        if search_text:
            if search_text.lower() not in txn.description.lower():
                continue

        # ── Date range ───────────────────────────────────────
        if date_from:
            d_from = datetime.strptime(date_from, "%Y-%m-%d")
            if txn.date < d_from:
                continue
        if date_to:
            d_to = datetime.strptime(date_to, "%Y-%m-%d")
            if txn.date > d_to:
                continue

        # ── Amount range ─────────────────────────────────────
        total = sum(s.amount for s in txn.splits if s.amount > 0)
        if amount_min is not None and total < amount_min:
            continue
        if amount_max is not None and total > amount_max:
            continue

        results.append(txn_id)

    return results


# ── Fixture for a manager with diverse transactions ────────────────


@pytest.fixture
def search_fixture() -> AccountManager:
    """A manager with transactions that have varied descriptions, dates,
    and amounts — useful for testing each filter dimension."""
    mgr = AccountManager(db=MockDB())

    checking = mgr.add_account("Checking", 1)
    food = mgr.add_account("Food", 5)
    rent = mgr.add_account("Rent", 5)
    salary = mgr.add_account("Salary", 4)

    mgr.add_transaction(
        datetime(2026, 1, 15), "Weekly groceries — Sprouts",
        [Split(food, 8500), Split(checking, -8500)],
    )
    mgr.add_transaction(
        datetime(2026, 2, 1), "Rent payment January",
        [Split(rent, 150000), Split(checking, -150000)],
    )
    mgr.add_transaction(
        datetime(2026, 2, 15), "Groceries at Costco",
        [Split(food, 12000), Split(checking, -12000)],
    )
    mgr.add_transaction(
        datetime(2026, 3, 1), "Paycheck — Acme Corp",
        [Split(salary, -250000), Split(checking, 250000)],
    )
    mgr.add_transaction(
        datetime(2026, 3, 5), "Rent payment February",
        [Split(rent, 150000), Split(checking, -150000)],
    )
    mgr.add_transaction(
        datetime(2026, 3, 15), "Small snack at 7-Eleven",
        [Split(food, 650), Split(checking, -650)],
    )
    mgr.add_transaction(
        datetime(2026, 4, 1), "Paycheck — Acme Corp",
        [Split(salary, -250000), Split(checking, 250000)],
    )

    mgr.generate_ledger()
    return mgr


# ── Description search ─────────────────────────────────────────────


class TestDescriptionSearch:
    """Filtering the journal by description text."""

    def test_search_by_word(self, search_fixture: AccountManager):
        """Match a word in the middle of a description."""
        ids = _filter_txns(search_fixture, search_text="Costco")
        assert len(ids) == 1
        desc = search_fixture.journal.transactions[ids[0]].description
        assert "Costco" in desc

    def test_search_case_insensitive(self, search_fixture: AccountManager):
        """Matching should not depend on case."""
        ids1 = _filter_txns(search_fixture, search_text="sprouts")
        ids2 = _filter_txns(search_fixture, search_text="Sprouts")
        assert ids1 == ids2
        assert len(ids1) == 1

    def test_search_partial_word(self, search_fixture: AccountManager):
        """Substring match — 'groc' should match 'Groceries'."""
        ids = _filter_txns(search_fixture, search_text="groc")
        assert len(ids) >= 1

    def test_search_multiple_matches(self, search_fixture: AccountManager):
        """Searching 'paycheck' should return both paydays."""
        ids = _filter_txns(search_fixture, search_text="paycheck")
        assert len(ids) == 2

    def test_search_no_match(self, search_fixture: AccountManager):
        """Non-existent text returns empty list."""
        ids = _filter_txns(search_fixture, search_text="zzzznonexistent")
        assert ids == []

    def test_search_none_returns_all(self, search_fixture: AccountManager):
        """None search text means no filter — return all."""
        ids = _filter_txns(search_fixture)
        assert len(ids) == len(search_fixture.journal.transactions)

    def test_search_empty_string_returns_all(self, search_fixture: AccountManager):
        """Empty string should be the same as None (no filter)."""
        ids = _filter_txns(search_fixture, search_text="")
        assert len(ids) == len(search_fixture.journal.transactions)

    def test_search_with_special_chars(self, search_fixture: AccountManager):
        """Special regex characters like '7-Eleven' should match literally."""
        ids = _filter_txns(search_fixture, search_text="7-Eleven")
        assert len(ids) == 1


# ── Date range filter ──────────────────────────────────────────────


class TestDateFilter:
    """Filtering the journal by date range."""

    def test_filter_date_from_only(self, search_fixture: AccountManager):
        """Only transactions on or after date_from should appear."""
        ids = _filter_txns(search_fixture, date_from="2026-03-01")
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            assert txn.date >= datetime(2026, 3, 1)

    def test_filter_date_to_only(self, search_fixture: AccountManager):
        """Only transactions on or before date_to should appear."""
        ids = _filter_txns(search_fixture, date_to="2026-02-15")
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            assert txn.date <= datetime(2026, 2, 15)

    def test_filter_date_range(self, search_fixture: AccountManager):
        """Transactions within the range [from, to]."""
        ids = _filter_txns(search_fixture, date_from="2026-02-01", date_to="2026-03-01")
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            assert datetime(2026, 2, 1) <= txn.date <= datetime(2026, 3, 1)

    def test_filter_date_same_day(self, search_fixture: AccountManager):
        """From == To should match only that day."""
        ids = _filter_txns(search_fixture, date_from="2026-03-01", date_to="2026-03-01")
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            assert txn.date == datetime(2026, 3, 1)

    def test_filter_date_no_match(self, search_fixture: AccountManager):
        """Range outside all transaction dates."""
        ids = _filter_txns(search_fixture, date_from="2027-01-01", date_to="2027-12-31")
        assert ids == []


# ── Amount range filter ────────────────────────────────────────────


class TestAmountFilter:
    """Filtering the journal by transaction total."""

    def test_filter_amount_min(self, search_fixture: AccountManager):
        """Only transactions with total >= amount_min."""
        ids = _filter_txns(search_fixture, amount_min=100000)
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            total = sum(s.amount for s in txn.splits if s.amount > 0)
            assert total >= 100000

    def test_filter_amount_max(self, search_fixture: AccountManager):
        """Only transactions with total <= amount_max."""
        ids = _filter_txns(search_fixture, amount_max=10000)
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            total = sum(s.amount for s in txn.splits if s.amount > 0)
            assert total <= 10000

    def test_filter_amount_range(self, search_fixture: AccountManager):
        """Transactions within amount range [min, max]."""
        ids = _filter_txns(search_fixture, amount_min=5000, amount_max=20000)
        for tid in ids:
            txn = search_fixture.journal.transactions[tid]
            total = sum(s.amount for s in txn.splits if s.amount > 0)
            assert 5000 <= total <= 20000


# ── Combined filters ───────────────────────────────────────────────


class TestCombinedFilters:
    """Filters applied together — should be intersection (AND)."""

    def test_description_and_date(self, search_fixture: AccountManager):
        """Only transactions matching BOTH description and date."""
        ids = _filter_txns(
            search_fixture,
            search_text="Rent",
            date_from="2026-03-01",
        )
        assert len(ids) == 1  # only February rent (March 5)
        desc = search_fixture.journal.transactions[ids[0]].description
        assert "Rent" in desc

    def test_description_and_amount(self, search_fixture: AccountManager):
        """Description + amount range."""
        ids = _filter_txns(
            search_fixture,
            search_text="paycheck",
            amount_min=200000,
        )
        assert len(ids) == 2  # both paychecks

    def test_all_filters_together(self, search_fixture: AccountManager):
        """Description + date + amount."""
        ids = _filter_txns(
            search_fixture,
            search_text="groc",
            date_from="2026-01-01",
            date_to="2026-02-28",
            amount_min=5000,
            amount_max=9000,
        )
        assert len(ids) == 1  # only "Weekly groceries — Sprouts" (Jan 15, $85)

    def test_no_filters_returns_all(self, search_fixture: AccountManager):
        """All None/empty filters = full journal."""
        ids = _filter_txns(search_fixture, search_text="", date_from="", date_to="",
                           amount_min=None, amount_max=None)
        assert len(ids) == len(search_fixture.journal.transactions)

    def test_empty_journal(self):
        """Filtering an empty journal returns empty list."""
        mgr = AccountManager(db=MockDB())
        ids = _filter_txns(mgr, search_text="anything")
        assert ids == []
