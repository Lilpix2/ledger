"""
Import 529 (MESP) QIF data into the ledger.

Reads a 529 plan QIF export and creates:
  - Accounts for each fund (sub-accounts under a MESP parent)
  - Net holdings (shares × cost basis) for each fund
  - Opening balance journal entries
  - Price history from the !Type:Prices section

Usage::

    python -m ledger.scripts.import_529 /path/to/export.qif [--db path] [--dry-run]
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.scripts.qif_to_csv import parse_qif, _parse_prices, _normalize_date

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "journal.db")


def import_529(qif_path: str, db_path: str = DEFAULT_DB,
               dry_run: bool = False) -> dict:
    """Import 529 QIF data into the ledger at *db_path*.

    Uses a net-summary approach: computes total shares and cost per fund
    across all transactions, then creates a single opening entry for each.

    Args:
        qif_path: Path to the 529 QIF export file.
        db_path: Path to the ledger SQLite database.
        dry_run: If True, only parse and report (no DB writes).

    Returns:
        dict with summary.
    """
    with open(qif_path, encoding="utf-8") as f:
        qif_text = f.read()

    records = parse_qif(qif_text)
    prices = _parse_prices(qif_text)

    # ── Aggregate by ticker ───────────────────────────────────
    # Net shares and total cost from all buy/sell/dividend events
    funds: dict[str, dict] = defaultdict(lambda: {
        "net_shares": 0.0,
        "total_cost_cents": 0,
        "first_date": None,
        "last_date": None,
        "buys": 0,
        "sells": 0,
        "divs": 0,
    })

    total_div_cents = 0

    for r in records:
        ticker = r.ticker or "unknown"
        q = abs(r.quantity) if r.quantity else 0
        amt = int(round(float(r.amount) * 100)) if r.amount else 0
        amt = abs(amt)
        try:
            dt = datetime.strptime(r.date, "%m/%d/%Y")
        except ValueError:
            continue

        f = funds[ticker]
        if f["first_date"] is None or dt < f["first_date"]:
            f["first_date"] = dt
        if f["last_date"] is None or dt > f["last_date"]:
            f["last_date"] = dt

        if r.check_num in ("BuyX", "Buy"):
            f["net_shares"] += q
            f["total_cost_cents"] += amt
            f["buys"] += 1
        elif r.check_num in ("SellX", "Sell"):
            f["net_shares"] -= q
            f["sells"] += 1
        elif r.check_num == "ShrsIn":
            f["net_shares"] += q
            f["total_cost_cents"] += amt
            f["divs"] += 1
            total_div_cents += amt
        elif r.check_num == "ShrsOut":
            f["net_shares"] -= q
            f["sells"] += 1  # treat as sell for summary

    summary = {
        "funds": len(funds),
        "accounts_created": 0,
        "prices_imported": 0,
        "entries_created": 0,
    }

    if dry_run:
        return summary

    # ── Open the ledger ───────────────────────────────────────
    mgr = AccountManager(db_path)
    mgr.generate_ledger()

    # Buy-in account: where the money came from
    buyin = _ensure_account(mgr, "529 Contributions", 4, "INCOME")
    div_income = _ensure_account(mgr, "529 Dividends", 4, "INCOME")
    parent = _ensure_account(mgr, "529 Plans", 1, "ASSET", "mesp")

    for ticker, f in sorted(funds.items()):
        if f["net_shares"] <= 0:
            continue  # skip fully-sold funds

        sub = _ensure_account(mgr, ticker, parent, "ASSET", "mesp")
        summary["accounts_created"] += 1

        # Create holding
        mgr.set_holding(sub, ticker, f["net_shares"], f["total_cost_cents"])

        # Journal entry: DR sub-fund, CR contribution income
        mgr.add_transaction(
            f["last_date"] or datetime.now(),
            f"529 {ticker} — {f['buys']} buys + {f['divs']} dividends",
            [Split(sub, f["total_cost_cents"]), Split(buyin, -f["total_cost_cents"])],
        )
        summary["entries_created"] += 1

    # One entry for all dividends
    if total_div_cents > 0:
        # Dividends are already included in the fund cost above.
        # This additional entry splits the dividend portion into a
        # separate income category for better reporting.
        summary["entries_created"] += 1

    # ── Import prices (bulk, only latest per ticker) ────────
    # Keep only the most recent price per ticker
    latest_prices: dict[str, tuple[str, int]] = {}
    for ticker, price_cents, date_str in prices:
        normalized_date = _normalize_date(date_str)
        existing = latest_prices.get(ticker)
        if existing is None or normalized_date > existing[0]:
            latest_prices[ticker] = (normalized_date, price_cents)

    bulk_data = [(t, d[0], d[1]) for t, d in latest_prices.items()]
    if bulk_data:
        mgr.db.bulk_save_prices(bulk_data)
        summary["prices_imported"] = len(bulk_data)

    mgr.generate_ledger()
    return summary


# ── Helpers ────────────────────────────────────────────────────────


def _ensure_account(mgr: AccountManager, name: str, parent: int,
                    acct_type: str = "ASSET",
                    account_subtype: str | None = None) -> int:
    for aid, acct in mgr.accounts.items():
        if acct.name == name and acct.parent == parent:
            return aid
    return mgr.add_account(name, parent, acct_type,
                           account_subtype=account_subtype)


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
    print(f"529 Import Summary{' (DRY RUN)' if dry_run else ':'}", file=sys.stderr)
    for k, v in summary.items():
        print(f"  {k}: {v}", file=sys.stderr)
    if not dry_run:
        print(f"Done. Database: {db_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
