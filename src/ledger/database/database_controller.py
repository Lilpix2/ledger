"""Controller for SQLite persistence of ledger data."""

import os
import sqlite3

from .create_table import ensure_tables


class DatabaseController:
    """Handles all SQLite operations for the ledger system."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        # Ensure the parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_tables(self):
        """Create tables if they don't exist (and migrate existing ones)."""
        with self._connect() as conn:
            ensure_tables(conn)
            # Migration: add acct_type column for existing databases
            try:
                conn.execute(
                    "ALTER TABLE accounts ADD COLUMN acct_type TEXT NOT NULL DEFAULT 'ASSET'"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

    def load_accounts(self) -> list[tuple[int, str, int | None, str]]:
        """Return list of (account_id, name, parent_id, acct_type) for all accounts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT account_id, name, parent_id, acct_type FROM accounts ORDER BY account_id"
            ).fetchall()
            return [
                (r["account_id"], r["name"], r["parent_id"], r["acct_type"])
                for r in rows
            ]

    def load_transactions(self) -> list[tuple[int, str, str, int, int, int]]:
        """Return list of (journal_id, date, description, credit_id, debit_id, amount)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT journal_id, date, description, credit_account_id, debit_account_id, amount FROM journal ORDER BY journal_id"
            ).fetchall()
            return [
                (
                    r["journal_id"],
                    r["date"],
                    r["description"],
                    r["credit_account_id"],
                    r["debit_account_id"],
                    r["amount"],
                )
                for r in rows
            ]

    def save_account(
        self, name: str, parent_id: int | None = None, acct_type: str = "ASSET"
    ) -> int:
        """Insert a new account and return its account_id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO accounts (name, parent_id, acct_type) VALUES (?, ?, ?)",
                (name, parent_id, acct_type),
            )
            return cur.lastrowid

    def save_transaction(
        self,
        date: str,
        description: str,
        credit_id: int,
        debit_id: int,
        amount: int,
    ) -> int:
        """Insert a new journal entry and return its journal_id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO journal (date, description, credit_account_id, debit_account_id, amount) VALUES (?, ?, ?, ?, ?)",
                (date, description, credit_id, debit_id, amount),
            )
            return cur.lastrowid
