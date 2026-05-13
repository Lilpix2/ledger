"""
Import a Beancount ledger file into the ledger TUI SQLite database.

Usage:
    python -m ledger.scripts.import_beancount /path/to/finances.bean
    python -m ledger.scripts.import_beancount /path/to/finances.bean --db custom.db
    python -m ledger.scripts.import_beancount /path/to/finances.bean --dry-run

This script:
    1. Creates Accounts matching the Beancount account tree
    2. Detects subtypes from Beancount account names
    3. Imports all Transactions as compound journal entries
    4. Computes Holdings (positions) from closing balances
    5. Imports Price directives as price quotes
    6. Runs generate_ledger() to verify the books balance
"""

import argparse
import sys
import os
from collections import defaultdict
from datetime import datetime

from beancount.loader import load_file
from beancount.core import data as bc_data
from beancount.core import getters
from beancount.core.inventory import Inventory
from beancount.core.amount import Amount
from beancount.core.number import Decimal  # noqa: F401 — used by eval

# ── Ledger imports ────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


# ── Subtype detection ─────────────────────────────────────────────

# Patterns: (keyword, subtype) — checked case-insensitively in the
# leaf account name.
SUBTYPE_PATTERNS = [
    ("checking", "checking"),
    ("savings", "checking"),
    ("credit", "credit_card"),
    ("discover", "credit_card"),
    ("brokerage", "brokerage"),
    ("schwab", "brokerage"),
    ("fidelity", "brokerage"),
    ("vanguard", "brokerage"),
    ("mesp", "mesp"),
    ("retirement", "retirement"),
    ("roth", "retirement"),
    ("ira", "retirement"),
    ("401k", "retirement"),
]


def detect_subtype(account_name: str) -> str | None:
    """Infer account subtype from the Beancount account name.

    Checks both the full path and the leaf name.
    """
    leaf = account_name.split(":")[-1].lower()
    full = account_name.lower()
    for keyword, subtype in SUBTYPE_PATTERNS:
        if keyword in leaf or keyword in full:
            return subtype
    return None


def beancount_type_to_ledger(account_name: str) -> str:
    """Map Beancount top-level type to ledger acct_type."""
    top = account_name.split(":")[0].upper()
    mapping = {
        "ASSETS": "ASSET",
        "LIABILITIES": "LIABILITY",
        "EQUITY": "EQUITY",
        "INCOME": "INCOME",
        "EXPENSES": "EXPENSE",
    }
    return mapping.get(top, "ASSET")


# ── Account tree builder ──────────────────────────────────────────


def _ensure_account_path(mgr: AccountManager, path: str, subtype: str | None = None) -> int:
    """Create all parent accounts along *path* (colon-separated).

    ``Assets:Checking:HS Checking`` creates:
      - Assets (already exists, ID 1)
      - Checking (parent=1)
      - HS Checking (parent=Checking, subtype=checking)

    Returns the ID of the leaf account.
    """
    parts = path.split(":")
    parent_id = 0  # root

    # Map top-level name to the standard parent ID
    top = parts[0].lower()
    id_map = {
        "assets": 1, "liabilities": 2, "equity": 3,
        "income": 4, "expenses": 5,
    }

    if top in id_map:
        parent_id = id_map[top]
        parts = parts[1:]  # skip the top-level parent
    else:
        # Unknown top level — map by type
        acct_type = beancount_type_to_ledger(path)
        for aid, acct in mgr.accounts.items():
            if aid == 0:
                continue
            if acct.name.lower() == parts[0].lower() and acct.parent == 0:
                parent_id = aid
                parts = parts[1:]
                break

    if not parts:
        return parent_id

    # Build the sub-account chain
    leaf_subtype = subtype
    for i, part in enumerate(parts):
        # Only apply subtype to the leaf (last component)
        sub = leaf_subtype if i == len(parts) - 1 else None

        # Check if this account already exists under the parent
        existing = None
        for aid, acct in mgr.accounts.items():
            if aid == 0:
                continue
            if acct.name.lower() == part.lower() and acct.parent == parent_id:
                existing = aid
                break

        if existing is not None:
            parent_id = existing
        else:
            acct_type = beancount_type_to_ledger(path)
            parent_id = mgr.add_account(part, parent_id, acct_type, account_subtype=sub)

    return parent_id


# ── Main import logic ─────────────────────────────────────────────


def import_beancount(
    bean_path: str,
    db_path: str = "data/journal.db",
    dry_run: bool = False,
) -> dict:
    """Import a Beancount file into the ledger TUI database.

    Returns a summary dict with counts of imported items.
    """
    print(f"Loading Beancount file: {bean_path}")
    entries, errors, _ = load_file(bean_path)

    # Filter out non-blocking errors
    real_errors = [e for e in errors if e.__class__.__name__ != "DeprecatedError"]
    if real_errors:
        print(f"⚠  {len(real_errors)} errors in Beancount file:")
        for e in real_errors[:10]:
            print(f"    {e.message}")
        if len(real_errors) > 10:
            print(f"    ... and {len(real_errors) - 10} more")
        if not dry_run:
            proceed = input("Continue anyway? [y/N] ")
            if proceed.lower() != "y":
                print("Aborted.")
                return {"status": "aborted"}

    # Separate entries by type
    opens: list[bc_data.Open] = []
    transactions: list[bc_data.Transaction] = []
    prices: list[bc_data.Price] = []
    balances: list[bc_data.Balance] = []
    closes: list[bc_data.Close] = []
    commodities: list[bc_data.Commodity] = []

    for entry in entries:
        if isinstance(entry, bc_data.Open):
            opens.append(entry)
        elif isinstance(entry, bc_data.Transaction):
            transactions.append(entry)
        elif isinstance(entry, bc_data.Price):
            prices.append(entry)
        elif isinstance(entry, bc_data.Balance):
            balances.append(entry)
        elif isinstance(entry, bc_data.Close):
            closes.append(entry)
        elif isinstance(entry, bc_data.Commodity):
            commodities.append(entry)

    print(f"  Opens: {len(opens)}, Transactions: {len(transactions)}")
    print(f"  Prices: {len(prices)}, Balances: {len(balances)}")

    if dry_run:
        print("\n── Dry run — no changes made ──")
        return {"status": "dry_run"}

    # Initialize the ledger database
    mgr = AccountManager(db_path)
    bc_to_ledger_id: dict[str, int] = {}  # Beancount account → ledger ID
    accounts_created = 0
    transactions_imported = 0
    prices_imported = 0

    # ── Phase 1: Create Accounts ────────────────────────────────────
    print("\n── Phase 1: Creating accounts ──")

    # Collect all unique account names from opens and transactions
    account_names: set[str] = set()
    for o in opens:
        account_names.add(o.account)
    for txn in transactions:
        for posting in txn.postings:
            account_names.add(posting.account)
    for b in balances:
        account_names.add(b.account)

    for name in sorted(account_names):
        subtype = detect_subtype(name)
        acct_type = beancount_type_to_ledger(name)
        acct_id = _ensure_account_path(mgr, name, subtype)
        bc_to_ledger_id[name] = acct_id
        accounts_created += 1
        subtype_tag = f" [{subtype}]" if subtype else ""
        print(f"  {name:45s} → ID {acct_id:3d} ({acct_type}{subtype_tag})")

    # ── Phase 2: Import Transactions ────────────────────────────────
    print(f"\n── Phase 2: Importing {len(transactions)} transactions ──")

    skipped_narration = 0
    skipped_commodity = 0
    skipped_balance = 0

    for i, txn in enumerate(transactions):
        narration = txn.narration or txn.payee or ""

        splits = []
        has_commodity = False

        for posting in txn.postings:
            if posting.account not in bc_to_ledger_id:
                # Create account on-the-fly
                subtype = detect_subtype(posting.account)
                acct_id = _ensure_account_path(mgr, posting.account, subtype)
                bc_to_ledger_id[posting.account] = acct_id
                accounts_created += 1
            else:
                acct_id = bc_to_ledger_id[posting.account]

            units = posting.units
            if units is None:
                continue

            currency = units.currency
            number = units.number

            # Convert to cents
            try:
                cents = int(round(float(number) * 100))
            except (ValueError, TypeError, OverflowError):
                cents = 0

            if cents == 0:
                continue

            # Track commodities (non-USD postings)
            if currency.upper() != "USD":
                has_commodity = True

            splits.append(Split(acct_id, cents, memo=currency))

        if not splits:
            skipped_narration += 1
            continue

        if has_commodity:
            skipped_commodity += 1
            continue

        # Check balance
        total = sum(s.amount for s in splits)
        if total != 0:
            skipped_balance += 1
            continue

        try:
            # Beancount date is a datetime.date, convert to datetime
            dt = datetime(txn.date.year, txn.date.month, txn.date.day)
            mgr.add_transaction(dt, narration, splits)
            transactions_imported += 1
        except ValueError as e:
            skipped_balance += 1

        if (i + 1) % 500 == 0:
            print(f"  ... {i + 1}/{len(transactions)} processed")

    print(f"  Imported: {transactions_imported}")
    if skipped_narration:
        print(f"  Skipped (no splits): {skipped_narration}")
    if skipped_commodity:
        print(f"  Skipped (commodity postings): {skipped_commodity}")
    if skipped_balance:
        print(f"  Skipped (unbalanced): {skipped_balance}")

    # ── Phase 3: Compute Holdings ───────────────────────────────────
    print(f"\n── Phase 3: Computing holdings ──")

    # Use getters to get all positions
    holdings_by_account = _compute_holdings(entries)
    holdings_imported = 0

    for acct_bc_name, positions in sorted(holdings_by_account.items()):
        acct_id = bc_to_ledger_id.get(acct_bc_name)
        if acct_id is None:
            continue

        for pos in positions:
            units = pos.units
            cost = pos.cost

            ticker = units.currency
            shares = float(units.number)
            cost_basis_cents = int(round(float(cost.number) * 100)) if cost else 0

            if shares <= 0:
                continue

            mgr.set_holding(acct_id, ticker, round(shares, 6), cost_basis_cents)
            holdings_imported += 1
            print(f"  {acct_bc_name:45s} → {ticker:12s} {shares:>10.4f} sh  "
                  f"cost: ${cost_basis_cents/100:>8,.2f}")

    print(f"  Holdings imported: {holdings_imported}")

    # ── Phase 4: Import Prices ──────────────────────────────────────
    print(f"\n── Phase 4: Importing prices ──")

    for price_entry in prices:
        ticker = price_entry.currency
        date_str = price_entry.date.strftime("%Y-%m-%d")
        try:
            price_cents = int(round(float(price_entry.amount.number) * 100))
        except (ValueError, TypeError, OverflowError):
            continue

        mgr.save_price(ticker, date_str, price_cents)
        prices_imported += 1

    print(f"  Prices imported: {prices_imported}")

    # ── Phase 5: Verify ─────────────────────────────────────────────
    print(f"\n── Phase 5: Verifying ledger ──")

    try:
        mgr.generate_ledger()
        eq = mgr.check_accounting_equation()
        nw = eq["net_worth"]
        print(f"  Net worth: ${nw/100:,.2f}")
        if eq["balanced"]:
            print(f"  ✅ Accounting equation balances!")
        else:
            print(f"  ⚠  Equation: A={eq['assets']} ≠ L={eq['liabilities']}+E={eq['equity']}+NI={eq['net_income']}")
            print(f"  Difference: {eq['lhs'] - eq['rhs']}")
    except Exception as e:
        print(f"  ⚠  Ledger generation error: {e}")

    print(f"\n{'═' * 60}")
    print(f"  Import complete!")
    print(f"  Accounts:  {accounts_created}")
    print(f"  Txn:       {transactions_imported}")
    print(f"  Holdings:  {holdings_imported}")
    print(f"  Prices:    {prices_imported}")
    print(f"{'═' * 60}")

    return {
        "status": "success",
        "accounts": accounts_created,
        "transactions": transactions_imported,
        "holdings": holdings_imported,
        "prices": prices_imported,
        "net_worth": mgr.get_net_worth() if hasattr(mgr, 'get_net_worth') else 0,
    }


# ── Holdings computation ────────────────────────────────────────────


def _compute_holdings(entries: list) -> dict[str, list]:
    """Compute net positions per account from all entries.

    Returns {account_name: [Position, ...]}
    """
    from beancount.core.inventory import Inventory
    from beancount.core import account as bc_account

    # Accumulate positions per account
    positions: dict[str, Inventory] = defaultdict(Inventory)

    for entry in entries:
        if not isinstance(entry, bc_data.Transaction):
            continue
        for posting in entry.postings:
            acct = posting.account
            if posting.units is None:
                continue

            currency = posting.units.currency
            if currency.upper() == "USD":
                continue  # Skip USD postings, only track commodities

            if posting.cost is not None:
                # Cost-basis posting
                from beancount.core.position import Position as BCPosition
                pos = BCPosition(posting.units, posting.cost)
                positions[acct].add_position(pos)
            else:
                # Non-cost posting (e.g., price conversion)
                positions[acct].add_amount(posting.units)

    # Reduce to final positions
    result = {}
    for acct, inv in positions.items():
        reduced = inv.reduce()
        if not reduced.is_empty():
            result[acct] = reduced.get_positions()

    return result


# ── CLI entry point ─────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Import a Beancount ledger into the ledger TUI database.",
    )
    parser.add_argument("bean_file", help="Path to the .bean file")
    parser.add_argument(
        "--db", "-d",
        default="data/journal.db",
        help="Path to the ledger TUI SQLite database (default: data/journal.db)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Parse and report without writing to the database",
    )

    args = parser.parse_args()

    if not os.path.exists(args.bean_file):
        print(f"Error: file not found: {args.bean_file}")
        sys.exit(1)

    summary = import_beancount(args.bean_file, args.db, args.dry_run)

    if summary.get("status") == "aborted":
        sys.exit(1)


if __name__ == "__main__":
    main()
