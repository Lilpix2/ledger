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
    description TEXT NOT NULL
);
"""

CREATE_SPLITS = """
CREATE TABLE IF NOT EXISTS split (
    split_id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL REFERENCES journal(journal_id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    amount INTEGER NOT NULL,
    memo TEXT NOT NULL DEFAULT ''
);
"""


def ensure_tables(conn):
    """Create tables if they don't exist (and migrate from old schema)."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(CREATE_ACCOUNTS)
    conn.execute(CREATE_JOURNAL)
    conn.execute(CREATE_SPLITS)
    conn.commit()

    # Migration: drop old single-split columns if they exist
    old_columns = ("credit_account_id", "debit_account_id")
    for col in old_columns:
        try:
            conn.execute(f"ALTER TABLE journal DROP COLUMN {col}")
        except conn.OperationalError:
            pass  # Already migrated or was never there
    try:
        conn.execute("ALTER TABLE journal DROP COLUMN amount")
    except conn.OperationalError:
        pass
    conn.commit()
