"""Shared test fixtures for the ledger test suite.

Performance note: each test creates its own SQLite DB (~3s overhead per test).
Run a subset with -k to target specific tests quickly.
"""

import tempfile
import os
from datetime import datetime

import pytest

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


# ── Per-function fixtures (clean DB every time) ─────────────────────


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
