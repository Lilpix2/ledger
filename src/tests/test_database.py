"""Unit tests for DatabaseController.

Tests SQLite persistence: account and transaction CRUD, holdings, prices.
Each test creates a fresh temp database for isolation.
"""

import os
import tempfile
import sqlite3
from datetime import datetime

import pytest

from ledger.database.database_controller import DatabaseController
from ledger.models.data_class import Split, JournalTransaction, Holding, Price
from ledger.constants import DATE_STR


# ── Helpers ──────────────────────────────────────────────────────────


def _fresh_db() -> DatabaseController:
    """Create a DatabaseController on a new temp file."""
    path = tempfile.mktemp(suffix=".db")
    db = DatabaseController(path)
    db.ensure_tables()
    return db


def _fresh_db_path() -> str:
    """Return a temp file path without creating the DB."""
    return tempfile.mktemp(suffix=".db")


def _ts(date_str: str) -> str:
    """Convert a YYYY-MM-DD date string to the DATE_STR format."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime(DATE_STR)


# ═══════════════════════════════════════════════════════════════════
#  Connection & Initialization
# ═══════════════════════════════════════════════════════════════════


class TestDatabaseInit:
    """DatabaseController startup — connection, directory creation, tables."""

    def test_connect_creates_directory(self):
        """_connect() creates the parent directory when it doesn't exist."""
        import shutil
        # Create a temp dir to hold our test structure
        base = tempfile.mkdtemp()
        subdir = os.path.join(base, "sub", "nested")
        path = os.path.join(subdir, "test.db")
        db = DatabaseController(path)
        conn = db._connect()
        try:
            assert os.path.isdir(subdir), f"Directory not created: {subdir}"
            assert os.path.isfile(path), f"DB file not created: {path}"
        finally:
            conn.close()
            os.unlink(path)
            shutil.rmtree(base)

    def test_ensure_tables_creates_accounts_table(self):
        """After ensure_tables(), the accounts table exists."""
        db = _fresh_db()
        try:
            conn = db._connect()
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r["name"] for r in tables}
            assert "accounts" in table_names
            assert "journal" in table_names
            assert "split" in table_names
            assert "holdings" in table_names
            assert "prices" in table_names
            conn.close()
        finally:
            os.unlink(db.db_path)

    def test_ensure_tables_is_idempotent(self):
        """Calling ensure_tables multiple times doesn't error."""
        db = _fresh_db()
        try:
            db.ensure_tables()
            db.ensure_tables()
            db.ensure_tables()
        finally:
            os.unlink(db.db_path)

    def test_ensure_tables_sets_foreign_keys(self):
        """PRAGMA foreign_keys is ON on new connections."""
        db = _fresh_db()
        try:
            conn = db._connect()
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            assert row[0] == 1, "Foreign keys not enabled"
            conn.close()
        finally:
            os.unlink(db.db_path)


# ═══════════════════════════════════════════════════════════════════
#  Account CRUD
# ═══════════════════════════════════════════════════════════════════


class TestDatabaseAccountCRUD:
    """Database-level account persistence."""

    def test_save_account_returns_id(self):
        db = _fresh_db()
        try:
            acct_id = db.save_account("Test Account", None, "ASSET", False, None)
            assert isinstance(acct_id, int)
            assert acct_id > 0
        finally:
            os.unlink(db.db_path)

    def test_save_and_load(self):
        db = _fresh_db()
        try:
            acct_id = db.save_account("Checking", None, "ASSET", False, "checking")
            rows = db.load_accounts()
            assert len(rows) == 1
            row_id, name, parent_id, acct_type, is_contra, subtype = rows[0]
            assert name == "Checking"
            assert acct_type == "ASSET"
            assert subtype == "checking"
            assert is_contra == 0
        finally:
            os.unlink(db.db_path)

    def test_save_with_parent(self):
        db = _fresh_db()
        try:
            parent = db.save_account("Assets", None, "ASSET", False, None)
            child = db.save_account("Cash", parent, "ASSET", False, None)
            rows = db.load_accounts()
            assert len(rows) == 2
            child_row = [r for r in rows if r[1] == "Cash"][0]
            assert child_row[2] == parent
        finally:
            os.unlink(db.db_path)

    def test_update_account(self):
        db = _fresh_db()
        try:
            acct_id = db.save_account("Old", None, "ASSET", False, None)
            db.update_account(acct_id, "New", None, "LIABILITY", "credit_card")
            rows = db.load_accounts()
            assert len(rows) == 1
            _, name, _, acct_type, _, subtype = rows[0]
            assert name == "New"
            assert acct_type == "LIABILITY"
            assert subtype == "credit_card"
        finally:
            os.unlink(db.db_path)

    def test_delete_account(self):
        db = _fresh_db()
        try:
            acct_id = db.save_account("Temp", None, "ASSET", False, None)
            db.delete_account(acct_id)
            rows = db.load_accounts()
            assert len(rows) == 0
        finally:
            os.unlink(db.db_path)

    def test_delete_account_removes_holdings(self):
        db = _fresh_db()
        try:
            acct_id = db.save_account("Brokerage", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(acct_id, "VTI", 100.0, 2750000))
            db.delete_account(acct_id)
            holdings = db.load_holdings()
            assert len(holdings) == 0
        finally:
            os.unlink(db.db_path)

    def test_save_contra_account(self):
        db = _fresh_db()
        try:
            acct_id = db.save_account(
                "Acc. Depreciation", None, "ASSET", True, None,
            )
            rows = db.load_accounts()
            _, _, _, _, is_contra, _ = rows[0]
            assert is_contra == 1
        finally:
            os.unlink(db.db_path)


# ═══════════════════════════════════════════════════════════════════
#  Transaction CRUD
# ═══════════════════════════════════════════════════════════════════


class TestDatabaseTransactionCRUD:
    """Database-level transaction persistence."""

    def test_save_transaction_returns_id(self):
        db = _fresh_db()
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Test",
                [Split(acct_a, 5000), Split(acct_b, -5000)],
            )
            assert isinstance(jid, int)
            assert jid > 0
        finally:
            os.unlink(db.db_path)

    def test_save_and_load_transactions(self):
        db = _fresh_db()
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Test Entry",
                [Split(acct_a, 5000), Split(acct_b, -5000)],
            )
            txns = db.load_transactions()
            assert len(txns) == 1
            txn = txns[0]
            assert txn.description == "Test Entry"
            assert len(txn.splits) == 2
        finally:
            os.unlink(db.db_path)

    def test_delete_transaction(self):
        db = _fresh_db()
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "To Delete",
                [Split(acct_a, 1000), Split(acct_b, -1000)],
            )
            db.delete_transaction(jid)
            txns = db.load_transactions()
            assert len(txns) == 0
        finally:
            os.unlink(db.db_path)

    def test_delete_transaction_removes_splits(self):
        """Deleting a transaction also deletes its split rows."""
        db = _fresh_db()
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Clean splits",
                [Split(acct_a, 1000), Split(acct_b, -1000)],
            )
            db.delete_transaction(jid)
            conn = db._connect()
            splits = conn.execute("SELECT * FROM split WHERE journal_id=?", (jid,)).fetchall()
            conn.close()
            assert len(splits) == 0
        finally:
            os.unlink(db.db_path)

    def test_load_transactions_with_splits(self):
        """load_transactions groups splits correctly by journal_id."""
        db = _fresh_db()
        try:
            a = db.save_account("A", None, "ASSET", False, None)
            b = db.save_account("B", None, "LIABILITY", False, None)
            c = db.save_account("C", None, "EQUITY", False, None)

            jid1 = db.save_transaction(
                _ts("2026-01-15"), "Two split",
                [Split(a, 5000), Split(b, -5000)],
            )
            jid2 = db.save_transaction(
                _ts("2026-01-16"), "Three split",
                [Split(a, 10000), Split(b, -3000), Split(c, -7000)],
            )

            txns = db.load_transactions()
            assert len(txns) == 2

            # Find by description
            txn_two = [t for t in txns if t.description == "Two split"][0]
            assert len(txn_two.splits) == 2
            txn_three = [t for t in txns if t.description == "Three split"][0]
            assert len(txn_three.splits) == 3
        finally:
            os.unlink(db.db_path)

    def test_wipe_splits_for_account(self):
        """_wipe_splits_for_account removes orphaned split rows."""
        db = _fresh_db()
        try:
            a = db.save_account("A", None, "ASSET", False, None)
            b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Wipe me",
                [Split(a, 1000), Split(b, -1000)],
            )
            # Wipe splits for account B
            db._wipe_splits_for_account(b)
            conn = db._connect()
            remaining = conn.execute(
                "SELECT * FROM split WHERE journal_id=?", (jid,)
            ).fetchall()
            conn.close()
            assert len(remaining) == 1
            assert remaining[0]["account_id"] == a
        finally:
            os.unlink(db.db_path)

    def test_wipe_splits_for_nonexistent_account(self):
        """_wipe_splits_for_account handles non-existent accounts gracefully."""
        db = _fresh_db()
        try:
            # Should not raise
            db._wipe_splits_for_account(99999)
        finally:
            os.unlink(db.db_path)


# ═══════════════════════════════════════════════════════════════════
#  Holdings & Prices
# ═══════════════════════════════════════════════════════════════════


class TestDatabaseHoldingsPrices:
    """Holding and price persistence."""

    def test_save_and_load_holdings_all(self):
        db = _fresh_db()
        try:
            a1 = db.save_account("B1", None, "ASSET", False, "brokerage")
            a2 = db.save_account("B2", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a1, "VTI", 100.0, 2750000))
            db.save_holding(Holding(a2, "AAPL", 50.0, 750000))
            all_h = db.load_holdings()
            assert len(all_h) == 2
        finally:
            os.unlink(db.db_path)

    def test_load_holdings_filtered_by_account(self):
        db = _fresh_db()
        try:
            a1 = db.save_account("B1", None, "ASSET", False, "brokerage")
            a2 = db.save_account("B2", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a1, "VTI", 100.0, 2750000))
            db.save_holding(Holding(a2, "AAPL", 50.0, 750000))
            filtered = db.load_holdings(account_id=a1)
            assert len(filtered) == 1
            assert filtered[0].ticker == "VTI"
        finally:
            os.unlink(db.db_path)

    def test_delete_holding(self):
        db = _fresh_db()
        try:
            a = db.save_account("B", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a, "VTI", 100.0, 2750000))
            db.delete_holding(a, "VTI")
            all_h = db.load_holdings()
            assert len(all_h) == 0
        finally:
            os.unlink(db.db_path)

    def test_save_and_load_prices_all(self):
        db = _fresh_db()
        try:
            db.save_price(Price("VTI", "2026-01-15", 25000))
            db.save_price(Price("VTI", "2026-02-15", 26000))
            db.save_price(Price("AAPL", "2026-01-15", 15000))
            all_p = db.load_prices()
            assert len(all_p) == 3
        finally:
            os.unlink(db.db_path)

    def test_load_prices_filtered_by_ticker(self):
        db = _fresh_db()
        try:
            db.save_price(Price("VTI", "2026-01-15", 25000))
            db.save_price(Price("VTI", "2026-02-15", 26000))
            db.save_price(Price("AAPL", "2026-01-15", 15000))
            vti_prices = db.load_prices(ticker="VTI")
            assert len(vti_prices) == 2
            aapl_prices = db.load_prices(ticker="AAPL")
            assert len(aapl_prices) == 1
        finally:
            os.unlink(db.db_path)

    def test_save_price_replaces_existing(self):
        """save_price updates rather than duplicates (INSERT OR REPLACE)."""
        db = _fresh_db()
        try:
            db.save_price(Price("VTI", "2026-01-15", 25000))
            db.save_price(Price("VTI", "2026-01-15", 26000))  # same ticker+date
            prices = db.load_prices(ticker="VTI")
            assert len(prices) == 1
            assert prices[0].price_cents == 26000
        finally:
            os.unlink(db.db_path)

    def test_bulk_save_prices(self):
        db = _fresh_db()
        try:
            db.bulk_save_prices([
                ("VTI", "2026-01-15", 25000),
                ("VTI", "2026-02-15", 26000),
                ("AAPL", "2026-01-15", 15000),
            ])
            prices = db.load_prices()
            assert len(prices) == 3
        finally:
            os.unlink(db.db_path)

    def test_bulk_save_prices_replaces(self):
        """bulk_save_prices replaces existing entries."""
        db = _fresh_db()
        try:
            db.bulk_save_prices([("VTI", "2026-01-15", 25000)])
            db.bulk_save_prices([("VTI", "2026-01-15", 26000)])
            prices = db.load_prices(ticker="VTI")
            assert len(prices) == 1
            assert prices[0].price_cents == 26000
        finally:
            os.unlink(db.db_path)

    def test_load_prices_empty_when_none(self):
        db = _fresh_db()
        try:
            prices = db.load_prices(ticker="NONEXIST")
            assert prices == []
        finally:
            os.unlink(db.db_path)

    def test_save_holding_replace(self):
        """Save holding replaces existing for same account+ticker."""
        db = _fresh_db()
        try:
            a = db.save_account("B", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a, "VTI", 100.0, 2750000))
            db.save_holding(Holding(a, "VTI", 200.0, 5500000))
            holdings = db.load_holdings(account_id=a)
            assert len(holdings) == 1
            assert holdings[0].shares == 200.0
        finally:
            os.unlink(db.db_path)

    def test_delete_nonexistent_holding(self):
        """Deleting a holding that doesn't exist doesn't raise."""
        db = _fresh_db()
        try:
            a = db.save_account("B", None, "ASSET", False, "brokerage")
            db.delete_holding(a, "NONEXIST")
        finally:
            os.unlink(db.db_path)


# ═══════════════════════════════════════════════════════════════════
#  Edge Cases
# ═══════════════════════════════════════════════════════════════════


class TestDatabaseEdgeCases:
    """Edge cases: empty DB, multiple tables, error handling."""

    def test_load_accounts_empty_db(self):
        db = _fresh_db()
        try:
            rows = db.load_accounts()
            assert rows == []
        finally:
            os.unlink(db.db_path)

    def test_load_transactions_empty_db(self):
        db = _fresh_db()
        try:
            txns = db.load_transactions()
            assert txns == []
        finally:
            os.unlink(db.db_path)

    def test_load_holdings_empty_db(self):
        db = _fresh_db()
        try:
            holdings = db.load_holdings()
            assert holdings == []
        finally:
            os.unlink(db.db_path)

    def test_load_prices_empty_db(self):
        db = _fresh_db()
        try:
            prices = db.load_prices()
            assert prices == []
        finally:
            os.unlink(db.db_path)

    def test_consecutive_connections(self):
        """Database works after multiple open/close cycles."""
        path = _fresh_db_path()
        try:
            db = DatabaseController(path)
            db.ensure_tables()
            a = db.save_account("A", None, "ASSET", False, None)
            # Re-create controller (simulates app restart)
            db2 = DatabaseController(path)
            rows = db2.load_accounts()
            assert len(rows) == 1
        finally:
            os.unlink(path)

    def test_isolation_between_databases(self):
        """Two different DB paths don't interfere."""
        path_a = _fresh_db_path()
        path_b = _fresh_db_path()
        try:
            dba = DatabaseController(path_a)
            dba.ensure_tables()
            dba.save_account("OnlyA", None, "ASSET", False, None)

            dbb = DatabaseController(path_b)
            dbb.ensure_tables()
            rows_b = dbb.load_accounts()
            assert len(rows_b) == 0
        finally:
            os.unlink(path_a)
            os.unlink(path_b)
