import sqlite3
foriegn = """
-- Enable foreign key support (specifically for SQLite)
PRAGMA foreign_keys = ON;
"""
journal = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER, -- Allowed to be NULL for top-level accounts
    FOREIGN KEY (parent_id) REFERENCES accounts (account_id)
);
"""
accounts = """
CREATE TABLE IF NOT EXISTS journal (
    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, -- Format: YYYY-MM-DD
    description TEXT NOT NULL,
    credit_account_id INTEGER NOT NULL,
    debit_account_id INTEGER NOT NULL,
    amount INTEGER NOT NULL, -- Stored in cents/smallest unit to avoid float errors
    FOREIGN KEY (credit_account_id) REFERENCES accounts (account_id),
    FOREIGN KEY (debit_account_id) REFERENCES accounts (account_id)
);
"""

with sqlite3.connect('data/journal.db') as conn:
    cur = conn.cursor()
    cur.execute(foriegn)
    cur.execute(journal)
    cur.execute(accounts)