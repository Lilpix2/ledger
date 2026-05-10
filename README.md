# Ledger

A double-entry accounting system with a terminal UI. Built with Python, persisted with SQLite, and driven by a Textual TUI.

```
┌─────────────────────────────────────┐
│  Ledger — Double-Entry Accounting   │
├──────────────┬──────────────────────┤
│  Accounts    │  Journal             │
│  ▼           │ Date  Description…   │
│  ├─ assets   │                     │
│  │  $1,250   │                     │
│  ├─ expenses │                     │
│  │  $500     │                     │
│  └─ …       │                     │
├──────────────┴──────────────────────┤
│ [A] Add Account  [T] Add Transaction│
│ [R] Refresh  [Q] Quit               │
└─────────────────────────────────────┘
```

## Quick Start

```bash
# Install
pip install textual
git clone https://github.com/Lilpix2/ledger.git
cd ledger
pip install -e .

# Or, install deps manually:
# pip install textual

# Run
ledger
```

**First run** seeds the five parent accounts and creates `data/journal.db`. All data persists automatically.

## Usage

### Keybindings

| Key | Action |
|-----|--------|
| `A` | Add account |
| `T` | Add transaction |
| `R` | Refresh tree & table |
| `Q` | Quit |

### Adding an Account

1. Press `A` → modal opens showing existing accounts with their IDs
2. Type the account name
3. Enter the parent account ID (e.g., `1` for Assets)
4. Submit — the tree updates immediately

### Adding a Transaction

1. Press `T` → modal opens showing accounts and a pre-filled date
2. **Date:** Click the 📅 button for a calendar, or type manually (`MM-DD-YYYY H:M:S`)
3. Fill in description, debit account ID, credit account ID, and amount (in cents)
4. Submit — both tree (balances) and journal table update

### Clicking an Account

Click any account in the tree to see a notification with:
- Account name
- Aggregate balance (sum of account + all descendants)
- Personal balance (transactions directly on this account)
- Parent account name

## Package Layout

```
src/ledger/
├── __init__.py
├── constants.py           # Date format, parent account names
├── main.py                # CLI demo script (used during development)
├── tui.py                 # Legacy terminal UI (input()-based)
├── tui_app.py             # Textual TUI (current)
│
├── controllers/
│   ├── __init__.py
│   └── accounts.py        # Account + AccountManager (business logic)
│
├── models/
│   ├── __init__.py
│   ├── data_class.py      # JournalTransaction, LedgerEntry dataclasses
│   └── data_books.py      # Journal, Ledger containers
│
└── database/
    ├── __init__.py
    ├── create_table.py     # SQL schema (accounts + journal tables)
    └── database_controller.py  # SQLite read/write layer
```

## Architecture

### Data Flow

```
User Input (TUI)
    │
    ▼
AccountManager (business logic)
    │                       
    ├──▶ In-memory dicts (accounts, journal)
    │                       
    ▼                       
DatabaseController (SQLite)
    │
    ▼
data/journal.db
```

**On startup:** DatabaseController loads all accounts and transactions from SQLite into `AccountManager`'s in-memory dicts. If the database is empty, it seeds the five parent accounts.

**On mutation:** Every `add_account()` and `add_transaction()` call writes to SQLite first, then adds to memory. The DB-assigned ID becomes the in-memory ID.

**On refresh:** `generate_ledger()` clears all ledger entries, walks every journal transaction in chronological order, and posts debit/credit entries to each account's ledger. A trial balance check ensures `Σ balances = 0`. If not, it raises an error.

### Accounts

Accounts form a hierarchical tree. The root (id 0) is virtual and never persisted. Children reference their parent by integer ID.

```
id:0  (root, virtual)
├── id:1  assets
│   └── id:6  checking
├── id:2  liabilities
├── id:3  equity
├── id:4  income
│   └── id:7  salary
└── id:5  expenses
    └── id:8  groceries
```

**Parent balance aggregation:** `AccountManager.aggregated_balance(account_id)` recursively sums the account's personal balance plus the total of all descendants. This means `assets` shows the combined value of everything under it.

### Transactions (Journal)

Each transaction is a double entry:
- One debit account (money goes in)
- One credit account (money comes out)
- Amount in **cents** (integer, no floating-point)

Example: `add_transaction(date, "Groceries", credit=1, debit=5, amount=2000)` means $20.00 moved from `assets` to `expenses → groceries`.

### Persistence

SQLite database at `data/journal.db` with two tables:

**`accounts` table:**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Account name (unique) |
| parent_id | INTEGER | FK → accounts.id (nullable) |

**`journal` table:**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| date | TEXT | ISO date string |
| description | TEXT | Transaction memo |
| credit_acct | INTEGER | FK → accounts.id |
| debit_acct | INTEGER | FK → accounts.id |
| amount | INTEGER | Transaction amount in cents |

Foreign keys are enforced. `PRAGMA foreign_keys = ON` runs on every connection.

## CLI Reference

```bash
# Run the TUI
ledger

# Or directly via module
python3 -m ledger.tui_app

# Legacy demo (no TUI, prints to terminal)
python3 -m ledger.main
```

## Development

```bash
# Install in editable mode
pip install -e .

# Start the app
ledger
```

### Testing

```bash
# Quick smoke test — verifies imports and DB creation
rm -rf data && PYTHONPATH=src python3 -m ledger.tui_app
# Ctrl+C to exit, data/ directory persists your state
```

## Technical Notes

- **All amounts are integers (cents).** No floating-point arithmetic anywhere in the system. Avoids rounding errors.
- **Date format:** `MM-DD-YYYY HH:MM:SS` (12-hour clock with seconds).
- **Trial balance enforced on every `generate_ledger()` call.** If debits ≠ credits, it raises an exception.
- **Modal-based input** via Textual's `ModalScreen`. Each add-account and add-transaction flow is a separate screen with validation.

## Roadmap

Ideas for future development:
- Edit/delete existing accounts and transactions
- Account detail view (show ledger for a single account)
- CSV/OFX import
- Report generation (income statement, balance sheet)
- Budget tracking
- Multi-user support
