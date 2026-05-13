"""
Import 529 (MESP) QIF data into the ledger.
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


def import_529(qif_path: str, db_path: str = DEFAULT_DB,
               dry_run: bool = False) -> dict:
    with open(qif_path, encoding="utf-8") as f:
        qif_text = f.read()

    records = parse_qif(qif_text)
    prices = _parse_prices(qif_text)

    # ── First pass: net-summary + record close-out amounts ───
    funds: dict[str, dict] = defaultdict(lambda: {
        "net_shares": 0.0, "total_cost_cents": 0, "last_date": None,
        "buys": 0, "sells": 0, "divs": 0, "closeout_events": [],
    })

    for r in records:
        ticker = r.ticker or "unknown"
        q = abs(r.quantity) if r.quantity else 0
        amt = abs(int(round(float(r.amount) * 100))) if r.amount else 0
        try:
            dt = datetime.strptime(r.date, "%m/%d/%Y")
        except ValueError:
            continue

        f = funds[ticker]
        if f["last_date"] is None or dt > f["last_date"]:
            f["last_date"] = dt

        if r.check_num in ("BuyX", "Buy"):
            f["net_shares"] += q
            f["total_cost_cents"] += amt
            f["buys"] += 1

        elif r.check_num in ("SellX", "Sell"):
            if f["net_shares"] > 0:
                old_shares = f["net_shares"]
                old_cost = f["total_cost_cents"]
                sell_shares = min(q, old_shares)
                fraction = sell_shares / old_shares
                removed = int(round(old_cost * fraction))
                f["total_cost_cents"] -= min(removed, old_cost)
                f["net_shares"] -= sell_shares
            f["sells"] += 1

        elif r.check_num == "ShrsIn":
            f["net_shares"] += q
            f["total_cost_cents"] += amt
            f["divs"] += 1

        elif r.check_num == "ShrsOut":
            memo = (r.memo or "").lower()
            if "conversion" in memo or "realign" in memo or "system" in memo:
                # Record the balance BEFORE zeroing for journal creation
                if f["total_cost_cents"] > 0:
                    f["closeout_events"].append({
                        "date": dt,
                        "close_amount": f["total_cost_cents"],
                    })
                f["net_shares"] = 0.0
                f["total_cost_cents"] = 0
            else:
                if f["net_shares"] > 0:
                    old_shares = f["net_shares"]
                    old_cost = f["total_cost_cents"]
                    sell_shares = min(q, old_shares)
                    fraction = sell_shares / old_shares
                    removed = int(round(old_cost * fraction))
                    f["total_cost_cents"] -= min(removed, old_cost)
                    f["net_shares"] -= sell_shares
            f["sells"] += 1

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

    # Clean slate
    mesp_acct_ids = {
        aid for aid, acct in mgr.accounts.items()
        if acct.account_subtype == "mesp"
        or acct.name in ("529 Contributions", "529 Dividends", "529 Fees")
    }
    for txn_id in list(mgr.journal.transactions.keys()):
        txn = mgr.journal.transactions[txn_id]
        if any(s.account_id in mesp_acct_ids for s in txn.splits):
            mgr.delete_transaction(txn_id)

    buyin = _ensure_account(mgr, "529 Contributions", 4, "INCOME")
    div_income = _ensure_account(mgr, "529 Dividends", 4, "INCOME")
    parent = _ensure_account(mgr, "529 Plans", 1, "ASSET", "mesp")

    # ── Create sub-accounts ───────────────────────────────────
    ticker_accts: dict[str, int] = {}
    for ticker in sorted({r.ticker for r in records if r.ticker}):
        sub = _ensure_account(mgr, ticker, parent, "ASSET", "mesp")
        ticker_accts[ticker] = sub
        summary["accounts_created"] += 1

    # ── Second pass: create journal entries per record ────────
    for r in records:
        ticker = r.ticker or "unknown"
        sub = ticker_accts.get(ticker)
        if sub is None:
            continue
        q = abs(r.quantity) if r.quantity else 0
        amt = abs(int(round(float(r.amount) * 100))) if r.amount else 0
        try:
            dt = datetime.strptime(r.date, "%m/%d/%Y")
        except ValueError:
            continue

        memo_lower = (r.memo or "").lower()
        is_closeout = any(w in memo_lower for w in ("conversion", "realign", "system"))

        try:
            if r.check_num in ("BuyX", "Buy"):
                mgr.add_transaction(dt, f"529 Buy {ticker}",
                    [Split(sub, amt), Split(buyin, -amt)])
                summary["entries_created"] += 1

            elif r.check_num in ("SellX", "Sell"):
                mgr.add_transaction(dt, f"529 Sell {ticker}",
                    [Split(buyin, amt), Split(sub, -amt)])
                summary["entries_created"] += 1

            elif r.check_num == "ShrsIn" and amt > 0:
                mgr.add_transaction(dt, f"529 Dividend {ticker}",
                    [Split(sub, amt), Split(div_income, -amt)])
                summary["entries_created"] += 1

            elif r.check_num == "ShrsOut" and is_closeout:
                # Use the close-out amount recorded in the first pass
                f = funds[ticker]
                for ev in f["closeout_events"]:
                    if ev["date"] == dt and ev["close_amount"] > 0:
                        mgr.add_transaction(dt, f"529 Rollover {ticker}",
                            [Split(buyin, ev["close_amount"]),
                             Split(sub, -ev["close_amount"])])
                        summary["entries_created"] += 1
                        break

            elif r.check_num == "ShrsOut" and not is_closeout and q > 0:
                mgr.add_transaction(dt, f"529 Transfer Out {ticker}",
                    [Split(div_income, amt) if amt > 0 else Split(buyin, 1),
                     Split(sub, -(amt if amt > 0 else 1))])
                summary["entries_created"] += 1

        except Exception:
            pass

    # ── Set holdings from net-summary ──────────────────────────
    for ticker, f in sorted(funds.items()):
        if f["net_shares"] <= 0 or f["total_cost_cents"] <= 0:
            continue
        sub = ticker_accts.get(ticker)
        if sub is not None:
            mgr.set_holding(sub, ticker, f["net_shares"], f["total_cost_cents"])

    # ── Import prices ─────────────────────────────────────────
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
