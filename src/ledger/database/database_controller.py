"""Controller for SQLite persistence of ledger data."""

import os
import sqlite3
from datetime import datetime

from ..constants import DATE_STR
from ..models.data_class import JournalTransaction, Split
from .create_table import ensure_tables


class DatabaseController:
    """Handles all SQLite operations for the ledger system."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_tables(self):
        with self._connect() as conn:
            ensure_tables(conn)

    def load_accounts(self) -> list[tuple[int, str, int | None, str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT account_id, name, parent_id, acct_type, is_contra "
                "FROM accounts ORDER BY account_id"
            ).fetchall()
            return [
                (r["account_id"], r["name"], r["parent_id"], r["acct_type"], r["is_contra"])
                for r in rows
            ]

    def load_transactions(self) -> list[JournalTransaction]:
        """Load all journal entries with their splits from the database."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT j.journal_id, j.date, j.description,
                       s.account_id, s.amount, s.memo
                FROM journal j
                JOIN split s ON s.journal_id = j.journal_id
                ORDER BY j.journal_id, s.split_id
            """).fetchall()

        # Group rows by journal_id
        journals: dict[int, dict] = {}
        for r in rows:
            jid = r["journal_id"]
            if jid not in journals:
                journals[jid] = {
                    "date": datetime.strptime(r["date"], DATE_STR),
                    "description": r["description"],
                    "splits": [],
                }
            journals[jid]["splits"].append(
                Split(r["account_id"], r["amount"], r["memo"] or "")
            )

        return [
            JournalTransaction(v["date"], v["description"], v["splits"])
            for v in journals.values()
        ]

    def save_account(
        self, name: str, parent_id: int | None = None, acct_type: str = "ASSET",
        is_contra: bool = False,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO accounts (name, parent_id, acct_type, is_contra) "
                "VALUES (?, ?, ?, ?)",
                (name, parent_id, acct_type, 1 if is_contra else 0),
            )
            return cur.lastrowid

    def save_transaction(
        self, date: str, description: str, splits: list[Split]
    ) -> int:
        """Insert a journal entry with its splits. Returns journal_id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO journal (date, description) VALUES (?, ?)",
                (date, description),
            )
            jid = cur.lastrowid
            for s in splits:
                conn.execute(
                    "INSERT INTO split (journal_id, account_id, amount, memo) "
                    "VALUES (?, ?, ?, ?)",
                    (jid, s.account_id, s.amount, s.memo),
                )
            return jid
