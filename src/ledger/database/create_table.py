"""SQLite table definitions for the ledger system."""

CREATE_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES accounts(account_id),
    acct_type TEXT NOT NULL DEFAULT 'ASSET'
);
"""

CREATE_JOURNAL = """
CREATE TABLE IF NOT EXISTS journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    credit_account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    debit_account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    amount INTEGER NOT NULL
);
"""


def ensure_tables(conn):
    """Create tables if they don't exist. Must be called per-connection."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(CREATE_ACCOUNTS)
    conn.execute(CREATE_JOURNAL)
    conn.commit()
