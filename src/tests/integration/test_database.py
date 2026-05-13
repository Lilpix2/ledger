"""Unit tests for DatabaseController.

Tests SQLite persistence: account and transaction CRUD, holdings, prices.
Each test creates a fresh temp database for isolation, with strict AAA
(Arrange / Act / Assert) separation and descriptive naming.
"""

import os
import sqlite3
import tempfile
from datetime import datetime

import pytest

from ledger.database.database_controller import DatabaseController
from ledger.models.data_class import Holding, JournalTransaction, Price, Split
from ledger.constants import DATE_STR


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fresh_db() -> DatabaseController:
    """Create a DatabaseController on a new temp file with tables created."""
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


def _cleanup(db: DatabaseController) -> None:
    """Delete the temp DB file if it exists."""
    try:
        os.unlink(db.db_path)
    except OSError:
        pass


def _cleanup_path(path: str) -> None:
    """Delete a file by path if it exists."""
    try:
        os.unlink(path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  Connection & Initialization
# ═══════════════════════════════════════════════════════════════════════════


class TestDatabaseInit:
    """DatabaseController startup — connection, directory creation, tables."""

    def test_connect_createsDirectory_whenMissing(self):
        """_connect() creates the parent directory when it doesn't exist."""
        # ── Arrange ──
        import shutil
        base = tempfile.mkdtemp()
        subdir = os.path.join(base, "sub", "nested")
        path = os.path.join(subdir, "test.db")
        db = DatabaseController(path)

        # ── Act ──
        conn = db._connect()

        # ── Assert ──
        try:
            assert os.path.isdir(subdir), f"Directory not created: {subdir}"
            assert os.path.isfile(path), f"DB file not created: {path}"
        finally:
            conn.close()
            _cleanup_path(path)
            shutil.rmtree(base)

    def test_ensureTables_createsRequiredTables(self):
        """After ensure_tables(), accounts, journal, split, holdings, prices exist."""
        # ── Arrange ──
        path = _fresh_db_path()
        db = DatabaseController(path)

        # ── Act ──
        db.ensure_tables()
        conn = db._connect()
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()

            # ── Assert ──
            table_names = {r["name"] for r in tables}
            assert "accounts" in table_names
            assert "journal" in table_names
            assert "split" in table_names
            assert "holdings" in table_names
            assert "prices" in table_names
        finally:
            conn.close()
            _cleanup_path(path)

    def test_ensureTables_isIdempotent(self):
        """Calling ensure_tables multiple times does not error."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act / Assert ──
        try:
            db.ensure_tables()
            db.ensure_tables()
            db.ensure_tables()
        finally:
            _cleanup(db)

    def test_ensureTables_setsForeignKeysOn(self):
        """PRAGMA foreign_keys is ON on new connections."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        conn = db._connect()
        try:
            row = conn.execute("PRAGMA foreign_keys").fetchone()

            # ── Assert ──
            assert row[0] == 1, "Foreign keys not enabled"
        finally:
            conn.close()
            _cleanup(db)


# ═══════════════════════════════════════════════════════════════════════════
#  Account CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestDatabaseAccountCRUD:
    """Database-level account persistence."""

    def test_saveAccount_returnsPositiveIntId(self):
        """save_account returns a positive integer ID."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_id = db.save_account("Test Account", None, "ASSET", False, None)

            # ── Assert ──
            assert isinstance(acct_id, int)
            assert acct_id > 0
        finally:
            _cleanup(db)

    def test_saveAndLoadAccount_persistsAllFields(self):
        """Saved account is retrievable with all fields intact."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.save_account("Checking", None, "ASSET", False, "checking")
            rows = db.load_accounts()

            # ── Assert ──
            assert len(rows) == 1
            row_id, name, parent_id, acct_type, is_contra, subtype = rows[0]
            assert name == "Checking"
            assert acct_type == "ASSET"
            assert subtype == "checking"
            assert is_contra == 0
        finally:
            _cleanup(db)

    def test_saveAccount_withParent_linksChildToParent(self):
        """Account saved with a parent_id loads with the correct parent reference."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            parent = db.save_account("Assets", None, "ASSET", False, None)
            child = db.save_account("Cash", parent, "ASSET", False, None)
            rows = db.load_accounts()

            # ── Assert ──
            assert len(rows) == 2
            child_row = [r for r in rows if r[1] == "Cash"][0]
            assert child_row[2] == parent
        finally:
            _cleanup(db)

    def test_updateAccount_changesAllMutableFields(self):
        """update_account overwrites name, type, and subtype."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_id = db.save_account("Old", None, "ASSET", False, None)
            db.update_account(acct_id, "New", None, "LIABILITY", "credit_card")
            rows = db.load_accounts()

            # ── Assert ──
            assert len(rows) == 1
            _, name, _, acct_type, _, subtype = rows[0]
            assert name == "New"
            assert acct_type == "LIABILITY"
            assert subtype == "credit_card"
        finally:
            _cleanup(db)

    def test_deleteAccount_removesRow(self):
        """Deleted account no longer appears in load_accounts."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_id = db.save_account("Temp", None, "ASSET", False, None)
            db.delete_account(acct_id)
            rows = db.load_accounts()

            # ── Assert ──
            assert len(rows) == 0
        finally:
            _cleanup(db)

    def test_deleteAccount_removesAssociatedHoldings(self):
        """Deleting an account also removes its holdings."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_id = db.save_account("Brokerage", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(acct_id, "VTI", 100.0, 2750000))
            db.delete_account(acct_id)
            holdings = db.load_holdings()

            # ── Assert ──
            assert len(holdings) == 0
        finally:
            _cleanup(db)

    def test_saveContraAccount_setsIsContraFlag(self):
        """An account saved with is_contra=True has is_contra=1 in the DB."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.save_account("Acc. Depreciation", None, "ASSET", True, None)
            rows = db.load_accounts()

            # ── Assert ──
            _, _, _, _, is_contra, _ = rows[0]
            assert is_contra == 1
        finally:
            _cleanup(db)


# ═══════════════════════════════════════════════════════════════════════════
#  Transaction CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestDatabaseTransactionCRUD:
    """Database-level transaction persistence."""

    def test_saveTransaction_returnsPositiveIntId(self):
        """save_transaction returns a positive integer journal_id."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Test",
                [Split(acct_a, 5000), Split(acct_b, -5000)],
            )

            # ── Assert ──
            assert isinstance(jid, int)
            assert jid > 0
        finally:
            _cleanup(db)

    def test_saveAndLoadTransaction_persistsWithSplits(self):
        """Saved transaction loads with correct description and splits."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            db.save_transaction(
                _ts("2026-01-15"), "Test Entry",
                [Split(acct_a, 5000), Split(acct_b, -5000)],
            )
            txns = db.load_transactions()

            # ── Assert ──
            assert len(txns) == 1
            txn = txns[0]
            assert txn.description == "Test Entry"
            assert len(txn.splits) == 2
        finally:
            _cleanup(db)

    def test_deleteTransaction_removesJournalEntry(self):
        """Deleted transaction no longer appears in load_transactions."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "To Delete",
                [Split(acct_a, 1000), Split(acct_b, -1000)],
            )
            db.delete_transaction(jid)
            txns = db.load_transactions()

            # ── Assert ──
            assert len(txns) == 0
        finally:
            _cleanup(db)

    def test_deleteTransaction_removesAssociatedSplitRows(self):
        """Deleting a transaction also deletes its associated split rows."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            acct_a = db.save_account("A", None, "ASSET", False, None)
            acct_b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Clean splits",
                [Split(acct_a, 1000), Split(acct_b, -1000)],
            )
            db.delete_transaction(jid)
            conn = db._connect()
            splits = conn.execute(
                "SELECT * FROM split WHERE journal_id=?", (jid,)
            ).fetchall()
            conn.close()

            # ── Assert ──
            assert len(splits) == 0
        finally:
            _cleanup(db)

    def test_loadTransactions_withMultipleJournals_groupsSplitsCorrectly(self):
        """load_transactions groups splits by journal_id for multi-split entries."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            a = db.save_account("A", None, "ASSET", False, None)
            b = db.save_account("B", None, "LIABILITY", False, None)
            c = db.save_account("C", None, "EQUITY", False, None)

            db.save_transaction(
                _ts("2026-01-15"), "Two split",
                [Split(a, 5000), Split(b, -5000)],
            )
            db.save_transaction(
                _ts("2026-01-16"), "Three split",
                [Split(a, 10000), Split(b, -3000), Split(c, -7000)],
            )
            txns = db.load_transactions()

            # ── Assert ──
            assert len(txns) == 2
            txn_two = [t for t in txns if t.description == "Two split"][0]
            assert len(txn_two.splits) == 2
            txn_three = [t for t in txns if t.description == "Three split"][0]
            assert len(txn_three.splits) == 3
        finally:
            _cleanup(db)

    def test_wipeSplitsForAccount_removesOnlyTargetAccountSplits(self):
        """_wipe_splits_for_account removes splits for the specified account only."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            a = db.save_account("A", None, "ASSET", False, None)
            b = db.save_account("B", None, "LIABILITY", False, None)
            jid = db.save_transaction(
                _ts("2026-01-15"), "Wipe me",
                [Split(a, 1000), Split(b, -1000)],
            )
            db._wipe_splits_for_account(b)
            conn = db._connect()
            remaining = conn.execute(
                "SELECT * FROM split WHERE journal_id=?", (jid,)
            ).fetchall()
            conn.close()

            # ── Assert ──
            assert len(remaining) == 1
            assert remaining[0]["account_id"] == a
        finally:
            _cleanup(db)

    def test_wipeSplitsForAccount_withNonexistentAccount_doesNotRaise(self):
        """_wipe_splits_for_account handles a non-existent account ID gracefully."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act / Assert ──
        try:
            db._wipe_splits_for_account(99999)
        finally:
            _cleanup(db)


# ═══════════════════════════════════════════════════════════════════════════
#  Holdings & Prices
# ═══════════════════════════════════════════════════════════════════════════


class TestDatabaseHoldingsPrices:
    """Holding and price persistence."""

    def test_saveAndLoadHoldings_returnsAll(self):
        """load_holdings without filter returns all saved holdings."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            a1 = db.save_account("B1", None, "ASSET", False, "brokerage")
            a2 = db.save_account("B2", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a1, "VTI", 100.0, 2750000))
            db.save_holding(Holding(a2, "AAPL", 50.0, 750000))
            all_h = db.load_holdings()

            # ── Assert ──
            assert len(all_h) == 2
        finally:
            _cleanup(db)

    def test_loadHoldings_filteredByAccount_returnsOnlyMatching(self):
        """load_holdings with account_id returns only matching records."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            a1 = db.save_account("B1", None, "ASSET", False, "brokerage")
            a2 = db.save_account("B2", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a1, "VTI", 100.0, 2750000))
            db.save_holding(Holding(a2, "AAPL", 50.0, 750000))
            filtered = db.load_holdings(account_id=a1)

            # ── Assert ──
            assert len(filtered) == 1
            assert filtered[0].ticker == "VTI"
        finally:
            _cleanup(db)

    def test_deleteHolding_removesFromDatabase(self):
        """Deleted holding no longer appears in load_holdings."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            a = db.save_account("B", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a, "VTI", 100.0, 2750000))
            db.delete_holding(a, "VTI")
            all_h = db.load_holdings()

            # ── Assert ──
            assert len(all_h) == 0
        finally:
            _cleanup(db)

    def test_saveAndLoadPrices_returnsAll(self):
        """load_prices without filter returns all saved prices."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.save_price(Price("VTI", "2026-01-15", 25000))
            db.save_price(Price("VTI", "2026-02-15", 26000))
            db.save_price(Price("AAPL", "2026-01-15", 15000))
            all_p = db.load_prices()

            # ── Assert ──
            assert len(all_p) == 3
        finally:
            _cleanup(db)

    def test_loadPrices_filteredByTicker_returnsOnlyMatching(self):
        """load_prices with ticker filter returns only matching records."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.save_price(Price("VTI", "2026-01-15", 25000))
            db.save_price(Price("VTI", "2026-02-15", 26000))
            db.save_price(Price("AAPL", "2026-01-15", 15000))
            vti_prices = db.load_prices(ticker="VTI")
            aapl_prices = db.load_prices(ticker="AAPL")

            # ── Assert ──
            assert len(vti_prices) == 2
            assert len(aapl_prices) == 1
        finally:
            _cleanup(db)

    def test_savePrice_withExistingKey_replacesEntry(self):
        """save_price replaces (does not duplicate) an existing ticker+date entry."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.save_price(Price("VTI", "2026-01-15", 25000))
            db.save_price(Price("VTI", "2026-01-15", 26000))  # same ticker+date
            prices = db.load_prices(ticker="VTI")

            # ── Assert ──
            assert len(prices) == 1
            assert prices[0].price_cents == 26000
        finally:
            _cleanup(db)

    def test_bulkSavePrices_insertsAllEntries(self):
        """bulk_save_prices inserts all provided price rows."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.bulk_save_prices([
                ("VTI", "2026-01-15", 25000),
                ("VTI", "2026-02-15", 26000),
                ("AAPL", "2026-01-15", 15000),
            ])
            prices = db.load_prices()

            # ── Assert ──
            assert len(prices) == 3
        finally:
            _cleanup(db)

    def test_bulkSavePrices_replacesExistingEntries(self):
        """bulk_save_prices replaces (does not duplicate) existing entries."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            db.bulk_save_prices([("VTI", "2026-01-15", 25000)])
            db.bulk_save_prices([("VTI", "2026-01-15", 26000)])
            prices = db.load_prices(ticker="VTI")

            # ── Assert ──
            assert len(prices) == 1
            assert prices[0].price_cents == 26000
        finally:
            _cleanup(db)

    def test_loadPrices_withNonexistentTicker_returnsEmptyList(self):
        """load_prices returns an empty list when no prices match the ticker."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            prices = db.load_prices(ticker="NONEXIST")

            # ── Assert ──
            assert prices == []
        finally:
            _cleanup(db)

    def test_saveHolding_withExistingKey_replacesEntry(self):
        """save_holding replaces existing entry for same account+ticker."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            a = db.save_account("B", None, "ASSET", False, "brokerage")
            db.save_holding(Holding(a, "VTI", 100.0, 2750000))
            db.save_holding(Holding(a, "VTI", 200.0, 5500000))
            holdings = db.load_holdings(account_id=a)

            # ── Assert ──
            assert len(holdings) == 1
            assert holdings[0].shares == 200.0
        finally:
            _cleanup(db)

    def test_deleteHolding_withNonexistent_doesNotRaise(self):
        """Deleting a holding that does not exist does not raise an exception."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act / Assert ──
        try:
            a = db.save_account("B", None, "ASSET", False, "brokerage")
            db.delete_holding(a, "NONEXIST")
        finally:
            _cleanup(db)


# ═══════════════════════════════════════════════════════════════════════════
#  Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestDatabaseEdgeCases:
    """Edge cases: empty DB, consecutive connections, isolation."""

    def test_loadAccounts_onEmptyDb_returnsEmptyList(self):
        """load_accounts returns [] on a fresh database."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            rows = db.load_accounts()

            # ── Assert ──
            assert rows == []
        finally:
            _cleanup(db)

    def test_loadTransactions_onEmptyDb_returnsEmptyList(self):
        """load_transactions returns [] on a fresh database."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            txns = db.load_transactions()

            # ── Assert ──
            assert txns == []
        finally:
            _cleanup(db)

    def test_loadHoldings_onEmptyDb_returnsEmptyList(self):
        """load_holdings returns [] on a fresh database."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            holdings = db.load_holdings()

            # ── Assert ──
            assert holdings == []
        finally:
            _cleanup(db)

    def test_loadPrices_onEmptyDb_returnsEmptyList(self):
        """load_prices returns [] on a fresh database."""
        # ── Arrange ──
        db = _fresh_db()

        # ── Act ──
        try:
            prices = db.load_prices()

            # ── Assert ──
            assert prices == []
        finally:
            _cleanup(db)

    def test_consecutiveConnections_persistsDataAcrossRestarts(self):
        """Database works and retains data after multiple open/close cycles."""
        # ── Arrange ──
        path = _fresh_db_path()

        # ── Act ──
        try:
            db = DatabaseController(path)
            db.ensure_tables()
            a = db.save_account("A", None, "ASSET", False, None)

            # Simulate app restart with a new controller
            db2 = DatabaseController(path)
            rows = db2.load_accounts()

            # ── Assert ──
            assert len(rows) == 1
        finally:
            _cleanup_path(path)

    def test_isolationBetweenDatabases_doesNotShareData(self):
        """Two different DB paths remain isolated from each other."""
        # ── Arrange ──
        path_a = _fresh_db_path()
        path_b = _fresh_db_path()

        # ── Act ──
        try:
            dba = DatabaseController(path_a)
            dba.ensure_tables()
            dba.save_account("OnlyA", None, "ASSET", False, None)

            dbb = DatabaseController(path_b)
            dbb.ensure_tables()
            rows_b = dbb.load_accounts()

            # ── Assert ──
            assert len(rows_b) == 0
        finally:
            _cleanup_path(path_a)
            _cleanup_path(path_b)
