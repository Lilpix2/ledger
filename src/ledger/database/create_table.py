"""SQLite table definitions for the ledger system."""

CREATE_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES accounts(account_id),
    acct_type TEXT NOT NULL DEFAULT 'ASSET',
    is_contra INTEGER NOT NULL DEFAULT 0,
    UNIQUE(name, parent_id)
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

CREATE_HOLDINGS = """
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    ticker TEXT NOT NULL,
    shares REAL NOT NULL DEFAULT 0.0,
    cost_basis_cents INTEGER NOT NULL DEFAULT 0,
    UNIQUE(account_id, ticker)
);
"""

CREATE_PRICES = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    UNIQUE(ticker, date)
);
"""


def _migrate_accounts_uniqueness(conn):
    """Replace global UNIQUE(name) with UNIQUE(name, parent_id).

    SQLite can't ALTER TABLE to drop a constraint, so we recreate the
    table when the old schema is detected.
    """
    # Detect old schema: check if we can insert a duplicate name under
    # a different parent. If the old constraint is in place, we need
    # to migrate.
    cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='accounts'")
    row = cursor.fetchone()
    if row and 'name TEXT NOT NULL UNIQUE' in row[0]:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""
            CREATE TABLE accounts_new (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER REFERENCES accounts(account_id),
                acct_type TEXT NOT NULL DEFAULT 'ASSET',
                is_contra INTEGER NOT NULL DEFAULT 0,
                account_subtype TEXT,
                UNIQUE(name, parent_id)
            )
        """)
        conn.execute("INSERT INTO accounts_new SELECT * FROM accounts")
        conn.execute("DROP TABLE accounts")
        conn.execute("ALTER TABLE accounts_new RENAME TO accounts")
        conn.execute("PRAGMA foreign_keys = ON")


def ensure_tables(conn):
    """Create tables if they don't exist (and migrate from old schema)."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(CREATE_ACCOUNTS)
    conn.execute(CREATE_JOURNAL)
    conn.execute(CREATE_SPLITS)
    conn.execute(CREATE_HOLDINGS)
    conn.execute(CREATE_PRICES)
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
    # Migration: add is_contra column to accounts
    try:
        conn.execute("ALTER TABLE accounts ADD COLUMN is_contra INTEGER NOT NULL DEFAULT 0")
    except conn.OperationalError:
        pass
    # Migration: add account_subtype column to accounts
    try:
        conn.execute("ALTER TABLE accounts ADD COLUMN account_subtype TEXT")
    except conn.OperationalError:
        pass
    # Migration: remove global UNIQUE on name, replace with (name, parent_id) UNIQUE
    _migrate_accounts_uniqueness(conn)
    conn.commit()
