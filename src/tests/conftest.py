"""Shared test fixtures for the ledger test suite.

Performance note: ``seeded_manager`` creates a real SQLite DB (~3s overhead).
Use ``fast_manager`` for pure unit tests (no disk I/O, milliseconds).
"""

import tempfile
import os
from datetime import datetime
from typing import Any

import pytest

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split, JournalTransaction, Holding, Price


# ── Mock DatabaseController (zero disk I/O) ────────────────────


class MockDB:
    """In-memory database mock — no disk I/O, sub-millisecond operations."""

    def __init__(self, db_path: str = "") -> None:
        self._accounts: dict[int, tuple[str, int | None, str, int, str | None]] = {}
        self._txns: list[tuple[str, str, list[Split]]] = []
        self._holdings: dict[int, dict[str, tuple[float, int]]] = {}
        self._prices: list[tuple[str, str, int]] = []
        self._next_id = 1

    def ensure_tables(self) -> None:
        pass

    def load_accounts(self) -> list[tuple[int, str, int | None, str, int, str | None]]:
        return []

    def load_transactions(self) -> list[JournalTransaction]:
        return []

    def load_holdings(self, account_id: int | None = None) -> list[Holding]:
        return []

    def load_prices(self, ticker: str | None = None) -> list[Price]:
        if ticker is None:
            return [Price(t, d, p) for t, d, p in self._prices]
        return [Price(t, d, p) for t, d, p in self._prices if t == ticker]

    def save_account(
        self, name: str, parent_id: int | None = None,
        acct_type: str = "ASSET", is_contra: bool = False,
        account_subtype: str | None = None,
    ) -> int:
        aid = self._next_id
        self._next_id += 1
        self._accounts[aid] = (name, parent_id, acct_type, 1 if is_contra else 0, account_subtype)
        return aid

    def update_account(
        self, acct_id: int, name: str,
        parent_id: int | None = None,
        acct_type: str | None = None,
        account_subtype: str | None = None,
    ) -> None:
        self._accounts[acct_id] = (name, parent_id, acct_type, 0, account_subtype)

    def delete_account(self, acct_id: int) -> None:
        self._accounts.pop(acct_id, None)

    def reassign_splits_in_db(self, source_id: int, target_id: int) -> None:
        """Move all split rows referencing *source_id* to *target_id*."""
        for i, (date, desc, splits) in enumerate(self._txns):
            for s in splits:
                if s.account_id == source_id:
                    s.account_id = target_id

    def reparent_children_in_db(self, old_parent_id: int, new_parent_id: int) -> None:
        """Reparent all direct children of *old_parent_id* to *new_parent_id*."""
        updated: list[tuple] = []
        for aid, (name, parent, acct_type, is_contra, subtype) in self._accounts.items():
            if parent == old_parent_id:
                updated.append((aid, name, new_parent_id, acct_type, is_contra, subtype))
            else:
                updated.append((aid, name, parent, acct_type, is_contra, subtype))
        for aid, name, parent, acct_type, is_contra, subtype in updated:
            self._accounts[aid] = (name, parent, acct_type, is_contra, subtype)

    def save_transaction(
        self, date: str, description: str, splits: list[Split]
    ) -> int:
        tid = self._next_id
        self._next_id += 1
        self._txns.append((date, description, splits))
        return tid

    def delete_transaction(self, txn_id: int) -> None:
        pass

    def _wipe_splits_for_account(self, acct_id: int) -> None:
        pass

    def save_holding(self, holding: Holding) -> None:
        aid = holding.account_id
        if aid not in self._holdings:
            self._holdings[aid] = {}
        self._holdings[aid][holding.ticker] = (holding.shares, holding.cost_basis_cents)

    def delete_holding(self, account_id: int, ticker: str) -> None:
        if account_id in self._holdings:
            self._holdings[account_id].pop(ticker, None)

    def save_price(self, price: Price) -> None:
        # Upsert: replace existing entry with same ticker+date
        for i, (t, d, p) in enumerate(self._prices):
            if t == price.ticker and d == price.date:
                self._prices[i] = (price.ticker, price.date, price.price_cents)
                return
        self._prices.append((price.ticker, price.date, price.price_cents))

    def bulk_save_prices(self, prices: list[tuple[str, str, int]]) -> None:
        self._prices.extend(prices)


@pytest.fixture
def fast_manager() -> AccountManager:
    """AccountManager with a mock DB — no disk I/O, runs in <1ms."""
    mgr = AccountManager(db=MockDB())
    yield mgr


@pytest.fixture
def fast_seeded() -> AccountManager:
    """Fast seeded manager with mock DB — income + expense + investment."""
    mgr = AccountManager(db=MockDB())
    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Wages", 4)
    mgr.add_account("Groceries", 5)

    ids = {a.name: aid for aid, a in mgr.accounts.items() if aid}

    mgr.add_transaction(
        datetime(2026, 1, 1), "Opening",
        [Split(ids["HS Checking"], 5000000),
         Split(ids["Savings"], 1000000),
         Split(ids["Schwab Brokerage"], 2000000),
         Split(ids["Discover"], -530000),
         Split(6, -7470000)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 1), "Payday",
        [Split(ids["Wages"], -300000), Split(ids["HS Checking"], 300000)],
    )
    mgr.add_transaction(
        datetime(2026, 6, 2), "Groceries",
        [Split(ids["Groceries"], 4500), Split(ids["HS Checking"], -4500)],
    )
    mgr.generate_ledger()
    yield mgr


@pytest.fixture
def manager() -> AccountManager:
    """A bare AccountManager with only the default accounts on a clean DB."""
    path = tempfile.mktemp(suffix=".db")
    mgr = AccountManager(path)
    yield mgr
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def seeded_manager() -> AccountManager:
    """A manager seeded with realistic accounts, holdings, and prices.

    Each call creates a fresh DB from scratch — this is expensive
    (~3s) but guarantees isolation between tests.
    """
    path = tempfile.mktemp(suffix=".db")
    mgr = _build_seeded(path)
    mgr._db_path = path
    yield mgr
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def ids(seeded_manager: AccountManager) -> dict[str, int]:
    """Resolve account names to IDs from the seeded manager."""
    return {acct.name: aid for aid, acct in seeded_manager.accounts.items() if aid}


# ── Builder ─────────────────────────────────────────────────────────


def _build_seeded(path: str) -> AccountManager:
    """Build and return a fully seeded AccountManager at *path*."""
    mgr = AccountManager(path)

    mgr.add_account("HS Checking", 1, account_subtype="checking")
    mgr.add_account("Savings", 1)
    mgr.add_account("Schwab Brokerage", 1, account_subtype="brokerage")
    mgr.add_account("Roth IRA", 1, account_subtype="retirement")
    mgr.add_account("MESP", 1, account_subtype="mesp")
    mgr.add_account("Discover", 2, account_subtype="credit_card")
    mgr.add_account("Capital Gains", 4)

    ids = {acct.name: aid for aid, acct in mgr.accounts.items() if aid}

    mgr.add_transaction(
        datetime(2026, 1, 1), "Opening balances",
        [
            Split(ids["HS Checking"], 5000000),
            Split(ids["Schwab Brokerage"], 2000000),
            Split(ids["Roth IRA"], 500000),
            Split(ids["MESP"], 10400000),
            Split(ids["Discover"], -530000),
            Split(6, -17370000),
        ],
    )

    mgr.buy_security(
        datetime(2026, 2, 1), "Buy VTI",
        ids["Schwab Brokerage"], ids["HS Checking"],
        "VTI", 100, 27500,
    )
    mgr.buy_security(
        datetime(2026, 3, 1), "Buy AAPL",
        ids["Schwab Brokerage"], ids["HS Checking"],
        "AAPL", 50, 15000,
    )
    mgr.buy_security(
        datetime(2026, 4, 1), "Buy VT",
        ids["Roth IRA"], ids["HS Checking"],
        "VT", 200, 10500,
    )

    mgr.save_price("VTI", "2026-05-13", 29000)
    mgr.save_price("AAPL", "2026-05-13", 16500)
    mgr.save_price("VT", "2026-05-13", 11000)

    mgr.account_ids = ids
    mgr.generate_ledger()
    return mgr
