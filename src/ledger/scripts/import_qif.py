"""
General QIF importer — handles all QIF file types.

Usage::

    python -m ledger.scripts.import_qif transactions.qif [--db path] [--dry-run]
    python -m ledger.scripts.import_qif /path/to/college_export [--account "College Checking"]
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.scripts.qif_to_csv import parse_qif, _parse_prices, _normalize_date

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "journal.db")


def import_qif(qif_path: str, db_path: str = DEFAULT_DB,
               account_name: str | None = None,
               dry_run: bool = False) -> dict:
    """Import any QIF file into the ledger.

    Auto-detects the QIF type and routes to the right handler.

    Args:
        qif_path: Path to QIF file.
        db_path: Ledger SQLite database path.
        account_name: Optional account name override for bank/ccard imports.
        dry_run: If True, parse and summarize without writing.

    Returns:
        Summary dict.
    """
    with open(qif_path, encoding="utf-8") as f:
        qif_text = f.read()

    records = parse_qif(qif_text)

    # Classify by section type
    types_present = {r.acct_type.lower() for r in records}
    has_bank = bool(types_present & {"bank", "ccard", "cash"})
    has_invst = "invst" in types_present

    summary = {
        "records_found": len(records),
        "type": "Unknown",
        "entries_created": 0,
        "dry_run": dry_run,
    }

    if dry_run:
        if has_bank:
            summary["type"] = "Bank/CCard"
        elif has_invst:
            summary["type"] = "Investment"
        return summary

    mgr = AccountManager(db_path)

    if has_bank:
        summary["type"] = "Bank/CCard"
        _import_bank(mgr, records, summary)
    elif has_invst:
        # Check if it's a 529 (has fund rollovers)
        tickers = {r.ticker for r in records if r.ticker}
        has_rollover = any(
            "conversion" in (r.memo or "").lower()
            for r in records if r.check_num == "ShrsOut"
        )
        if has_rollover:
            # 529 — use specialized importer
            summary["type"] = "529/MESP"
            from ledger.scripts.import_529 import import_529 as import_529_inner
            inner = import_529_inner(qif_path, db_path, dry_run=False)
            summary.update(inner)
        else:
            summary["type"] = "Brokerage"
            _import_brokerage(mgr, records, summary)

    mgr.generate_ledger()
    return summary


# ── Bank/CCard handler ────────────────────────────────────────────


def _import_bank(mgr: AccountManager, records: list,
                 summary: dict) -> None:
    """Import Bank/CCard/Cash QIF records as journal entries.

    Each record becomes a simple 2-split transaction. Category
    lines are parsed into ledger account paths.
    """
    # Build income/expense accounts from categories seen
    cat_accounts: dict[str, int] = {}
    parent_assets = 1
    parent_income = 4
    parent_expenses = 5

    for r in records:
        if not r.category:
            continue
        cat = r.category
        if cat not in cat_accounts:
            cat_accounts[cat] = _ensure_category(mgr, cat, parent_income,
                                                  parent_expenses, parent_assets)

    for r in records:
        if not r.amount:
            continue
        try:
            amt_cents = int(round(float(r.amount) * 100))
        except (ValueError, TypeError):
            continue
        if amt_cents == 0:
            continue
        try:
            dt = datetime.strptime(r.date, "%m/%d/%Y")
        except ValueError:
            continue

        # Determine the account pair
        cat = r.category or ""
        if cat.startswith("["):
            # Transfer to/from another account (e.g. [Alex College XX3233])
            acct_name = cat.strip("[]")
            target = _ensure_named_asset(mgr, acct_name)
            if amt_cents > 0:
                # Money in — DR target, CR income
                mgr.add_transaction(dt, r.payee or "Transfer",
                    [Split(target, amt_cents),
                     Split(cat_accounts.get("Income:Transfer",
                            _ensure_income(mgr, "Income:Transfer")), -amt_cents)])
            else:
                # Money out — DR expense, CR target
                mgr.add_transaction(dt, r.payee or "Transfer",
                    [Split(cat_accounts.get("Expenses:Transfers",
                            _ensure_expense(mgr, "Expenses:Transfers")), abs(amt_cents)),
                     Split(target, amt_cents)])
            summary["entries_created"] += 1
        elif amt_cents > 0:
            # Income: DR asset, CR income category
            inc_acct = cat_accounts.get(cat, _ensure_income(mgr, "Income:Misc"))
            mgr.add_transaction(dt, r.payee or "Income",
                [Split(1, amt_cents), Split(inc_acct, -amt_cents)])
            summary["entries_created"] += 1
        else:
            # Expense: DR expense category, CR asset
            out = abs(amt_cents)
            exp_acct = cat_accounts.get(cat, _ensure_expense(mgr, "Expenses:Misc"))
            mgr.add_transaction(dt, r.payee or "Expense",
                [Split(exp_acct, out), Split(1, -out)])
            summary["entries_created"] += 1


def _ensure_category(mgr: AccountManager, cat: str,
                     parent_income: int, parent_exp: int,
                     parent_assets: int) -> int:
    """Find or create an account for a category path like "Kids:Income/Alex"."""
    if cat.startswith("["):
        parts = cat.strip("[]").split(":")
        parent = parent_assets
        for p in parts:
            aid = _find_or_create(mgr, p.strip(), parent, "ASSET")
            parent = aid
        return parent
    if ":" in cat:
        parts = cat.split(":")
        # Check if first token is asset/income/expense-like
        first = parts[0].lower()
        if first in ("kids", "assets", "receivables"):
            parent = parent_assets
            acct_type = "ASSET"
        elif first in ("income",):
            parent = parent_income
            acct_type = "INCOME"
        else:
            parent = parent_exp
            acct_type = "EXPENSE"
        for p in parts:
            aid = _find_or_create(mgr, p.strip(), parent, acct_type)
            parent = aid
        return parent
    return _find_or_create(mgr, cat, parent_exp, "EXPENSE")


def _ensure_named_asset(mgr: AccountManager, name: str) -> int:
    return _find_or_create(mgr, name, 1, "ASSET")


def _ensure_income(mgr: AccountManager, name: str) -> int:
    return _find_or_create(mgr, name, 4, "INCOME")


def _ensure_expense(mgr: AccountManager, name: str) -> int:
    return _find_or_create(mgr, name, 5, "EXPENSE")


def _find_or_create(mgr: AccountManager, name: str, parent: int,
                    acct_type: str = "ASSET") -> int:
    for aid, a in mgr.accounts.items():
        if a.name.lower().strip() == name.lower().strip() and a.parent == parent:
            return aid
    return mgr.add_account(name.strip(), parent, acct_type)


# ── Brokerage handler ─────────────────────────────────────────────


def _import_brokerage(mgr: AccountManager, records: list,
                      summary: dict) -> None:
    """Import brokerage/retirement QIF Invst records.

    Handles Cash, Div, ReinvDiv, XIn, XOut, Buy, Sell actions.
    """
    mgr.generate_ledger()

    # Collect tickers and account names
    tickers = {r.ticker for r in records if r.ticker}
    broker_parent = _find_or_create(mgr, "Brokerage", 1, "ASSET")
    cash_source = _find_or_create(mgr, "Brokerage Cash", 1, "ASSET")
    div_income = _find_or_create(mgr, "Brokerage Dividends", 4, "INCOME")

    for r in records:
        action = (r.check_num or "").strip()
        try:
            amt_cents = int(round(float(r.amount) * 100)) if r.amount else 0
        except (ValueError, TypeError):
            amt_cents = 0
        try:
            dt = datetime.strptime(r.date, "%m/%d/%Y")
        except ValueError:
            continue

        if action == "Cash":
            # Cash movement into the brokerage
            mgr.add_transaction(dt, r.payee or "Cash Deposit",
                [Split(cash_source, abs(amt_cents)),
                 Split(div_income, -abs(amt_cents))])
            summary["entries_created"] += 1

        elif action == "Div":
            # Dividend received
            mgr.add_transaction(dt, r.payee or f"Dividend {r.ticker}",
                [Split(cash_source, abs(amt_cents)),
                 Split(div_income, -abs(amt_cents))])
            summary["entries_created"] += 1

        elif action == "ReinvDiv":
            # Dividend reinvested — DR position, CR income
            ticker = r.ticker or "Unknown"
            pos_acct = _find_or_create(mgr, ticker, broker_parent, "ASSET")
            qty = abs(r.quantity) if r.quantity else 0
            mgr.add_transaction(dt, r.payee or f"Reinvest {ticker}",
                [Split(pos_acct, abs(amt_cents)),
                 Split(div_income, -abs(amt_cents))])
            if qty > 0:
                holding = _get_holding(mgr, pos_acct, ticker)
                new_shares = holding + qty
                new_cost = abs(amt_cents)
                mgr.set_holding(pos_acct, ticker, new_shares, new_cost)
            summary["entries_created"] += 1

        elif action in ("XIn", "XOut"):
            # Transfer in/out
            ticker = r.ticker or "Brokerage"
            pos_acct = _find_or_create(mgr, ticker, broker_parent, "ASSET")
            if action == "XIn":
                mgr.add_transaction(dt, r.payee or "Transfer In",
                    [Split(pos_acct, abs(amt_cents)),
                     Split(div_income, -abs(amt_cents))])
            else:
                mgr.add_transaction(dt, r.payee or "Transfer Out",
                    [Split(div_income, abs(amt_cents)),
                     Split(pos_acct, -abs(amt_cents))])
            summary["entries_created"] += 1


def _get_holding(mgr: AccountManager, acct_id: int,
                 ticker: str) -> float:
    holdings = mgr.get_holdings(acct_id)
    for h in holdings:
        if h.ticker == ticker:
            return h.shares
    return 0.0


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(0 if not argv else 1)
    qif_path = argv[0]
    db_path = DEFAULT_DB
    account_name = None
    dry_run = False
    if "--db" in argv:
        idx = argv.index("--db"); db_path = argv[idx + 1]
    if "--account" in argv:
        idx = argv.index("--account"); account_name = argv[idx + 1]
    if "--dry-run" in argv:
        dry_run = True
    summary = import_qif(qif_path, db_path, account_name, dry_run=dry_run)
    print(f"Import Summary{' (DRY RUN)' if dry_run else ':'}", file=sys.stderr)
    for k, v in summary.items():
        print(f"  {k}: {v}", file=sys.stderr)
    if not dry_run:
        print(f"Done. Database: {db_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
