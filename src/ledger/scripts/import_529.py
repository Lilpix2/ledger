"""
Import 529 (MESP) QIF data into the ledger.

Reads a 529 plan QIF export and creates:
  - Accounts for each fund (sub-accounts under a MESP parent)
  - Journal entries for buys, sells, dividends, and adjustments
  - Holdings (positions) for each fund
  - Price history from the !Type:Prices section

Usage::

    python -m ledger.scripts.import_529 /path/to/export.qif [--db data/journal.db]
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from typing import TextIO

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.scripts.qif_to_csv import parse_qif, _parse_prices, _normalize_date

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "journal.db")


def import_529(qif_path: str, db_path: str = DEFAULT_DB,
               dry_run: bool = False) -> dict:
    """Import 529 QIF data into the ledger at *db_path*.

    Args:
        qif_path: Path to the 529 QIF export file.
        db_path: Path to the ledger SQLite database.
        dry_run: If True, only parse and report (no DB writes).

    Returns:
        dict with summary::
            {
                "accounts_created": int,
                "buys": int,
                "sells": int,
                "dividends": int,
                "adjustments": int,
                "prices_imported": int,
                "entries_created": int,
            }
    """
    with open(qif_path, encoding="utf-8") as f:
        qif_text = f.read()

    records = parse_qif(qif_text)
    prices = _parse_prices(qif_text)

    summary = {
        "accounts_created": 0,
        "buys": 0,
        "sells": 0,
        "dividends": 0,
        "adjustments": 0,
        "prices_imported": 0,
        "entries_created": 0,
    }

    if dry_run:
        summary["entries_created"] = len(records)
        summary["prices_imported"] = len(prices)
        return summary

    # Open the ledger
    mgr = AccountManager(db_path)
    mgr.generate_ledger()

    # Ensure MESP parent account exists
    mesp_parent = _ensure_account(mgr, "529 Plans", 1, "ASSET", "mesp")
    cash_source = _ensure_account(mgr, "529 Cash Source", 1, "ASSET", "checking")
    div_income = _ensure_account(mgr, "529 Dividends", 4, "INCOME")
    fee_expense = _ensure_account(mgr, "529 Fees", 5, "EXPENSE")

    ticker_accts: dict[str, int] = {}

    for r in records:
        ticker = r.ticker
        if ticker and ticker not in ticker_accts:
            sub = _ensure_account(mgr, ticker, mesp_parent, "ASSET", "mesp")
            ticker_accts[ticker] = sub
            summary["accounts_created"] += 1

        amount_cents = int(round(float(r.amount) * 100)) if r.amount else 0
        action = r.check_num

        try:
            date = datetime.strptime(r.date, "%m/%d/%Y")
        except ValueError:
            continue

        if action in ("BuyX", "Buy"):
            sub = ticker_accts.get(ticker)
            if sub is None or amount_cents <= 0:
                continue
            # Use Q (shares) and I (price) for the buy
            shares = abs(r.quantity) if r.quantity else 0
            price_cents = int(round(r.price * 100)) if r.price else 0
            if shares <= 0 or price_cents <= 0:
                # Estimate from total amount as fallback
                price_cents = amount_cents
                shares = 1
            mgr.buy_security(
                date, r.payee or f"Buy {ticker}",
                sub, cash_source, ticker, shares, price_cents,
            )
            summary["buys"] += 1
            summary["entries_created"] += 1

        elif action in ("SellX", "Sell"):
            sub = ticker_accts.get(ticker)
            if sub is None or amount_cents <= 0:
                continue
            shares = abs(r.quantity) if r.quantity else 0
            if shares <= 0:
                continue
            # Use the total amount (T) divided by shares as the price.
            # If T isn't available, try the unit price (I).
            if amount_cents > 0 and shares > 0:
                price_cents = int(round(amount_cents / shares))
            elif r.price:
                price_cents = int(round(r.price * 100))
            else:
                continue
            mgr.sell_security(
                date, r.payee or f"Sell {ticker}",
                sub, cash_source, ticker, shares, price_cents,
            )
            summary["sells"] += 1
            summary["entries_created"] += 1

        elif action == "ShrsIn":
            sub = ticker_accts.get(ticker)
            if sub is None or amount_cents <= 0:
                continue
            # Dividend/income reinvestment: DR fund, CR income
            mgr.add_transaction(
                date, r.payee or f"Dividend {ticker}",
                [Split(sub, amount_cents),
                 Split(div_income, -amount_cents)],
            )
            # Update holding manually (the entry doesn't create a holding)
            h = _get_or_create_holding(mgr, sub, ticker, r.quantity)
            summary["dividends"] += 1
            summary["entries_created"] += 1

        elif action in ("ShrsOut",):
            sub = ticker_accts.get(ticker)
            if sub is None:
                continue
            # Fee/adjustment: DR expense, CR fund
            amount_cents = int(round(
                (r.quantity or 0) * (r.price or 0) * 100
            )) if r.quantity and r.price else 0
            if amount_cents <= 0:
                continue
            mgr.add_transaction(
                date, r.payee or f"Adjustment {ticker}",
                [Split(sub, amount_cents),
                 Split(fee_expense, -amount_cents)],
            )
            summary["adjustments"] += 1
            summary["entries_created"] += 1

    # Import prices — normalize dates so lexicographic sort = chronological
    for ticker, price_cents, date_str in prices:
        normalized_date = _normalize_date(date_str)
        mgr.save_price(ticker, normalized_date, price_cents)
        summary["prices_imported"] += 1

    mgr.generate_ledger()
    return summary


# ── Helpers ────────────────────────────────────────────────────────


def _ensure_account(mgr: AccountManager, name: str, parent: int,
                    acct_type: str = "ASSET",
                    account_subtype: str | None = None) -> int:
    """Find or create an account by name under *parent*."""
    for aid, acct in mgr.accounts.items():
        if acct.name == name and acct.parent == parent:
            return aid
    return mgr.add_account(name, parent, acct_type,
                           account_subtype=account_subtype)


def _get_or_create_holding(mgr: AccountManager, account_id: int,
                           ticker: str, shares: float) -> None:
    """Update or create a holding, adding shares to the existing position."""
    existing = mgr.get_holdings(account_id)
    for h in existing:
        if h.ticker == ticker:
            new_shares = h.shares + abs(shares)
            new_cost = h.cost_basis_cents + int(round(
                abs(shares) * (mgr._avg_cost_basis(account_id, ticker) or 0)
            ))
            mgr.set_holding(account_id, ticker, new_shares, new_cost)
            return
    # New holding
    cost = int(round(abs(shares) * 100))  # placeholder cost basis
    mgr.set_holding(account_id, ticker, abs(shares), cost)


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(0 if not argv else 1)

    qif_path = argv[0]
    db_path = DEFAULT_DB
    dry_run = False

    if "--db" in argv:
        idx = argv.index("--db")
        db_path = argv[idx + 1]
    if "--dry-run" in argv:
        dry_run = True

    summary = import_529(qif_path, db_path, dry_run=dry_run)

    print(f"529 Import Summary{' (DRY RUN)' if dry_run else ''}:", file=sys.stderr)
    for key, val in summary.items():
        print(f"  {key}: {val}", file=sys.stderr)

    if not dry_run:
        print(f"Done. Database: {db_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
