"""
QIF → CSV converter.

Parses QIF (Quicken Interchange Format) files and outputs clean CSV
with one row per transaction.

Supports the following QIF section types:
  - !Type:Bank, !Type:CCard, !Type:Cash  → transaction output
  - !Type:Invst                           → transaction output
  - !Type:Security, !Type:Prices          → skipped (non-transaction)
  - !Account, !Type:Oth L, !Option, !Type:QIF → skipped

Date formats handled:
  - MM/DD/YYYY (standard)
  - MM/DD'YY   (apostrophe = 2-digit year, e.g. 5/16'17 → 05/16/2017)
"""

from __future__ import annotations

import csv
import io
import re
import sys
from dataclasses import dataclass, field
from typing import TextIO


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

TRANSACTION_TYPES = frozenset({"bank", "ccard", "cash", "invst"})


# ═══════════════════════════════════════════════════════════════════
#  QIFRecord
# ═══════════════════════════════════════════════════════════════════


@dataclass
class QIFRecord:
    """A single parsed QIF transaction."""

    date: str = ""
    amount: str = ""
    payee: str = ""
    memo: str = ""
    category: str = ""
    acct_type: str = ""
    check_num: str = ""
    cleared: str = ""
    ticker: str = ""
    quantity: float = 0.0  # Q field — number of shares
    price: float = 0.0     # I field — price per share


# ═══════════════════════════════════════════════════════════════════
#  Date helpers
# ═══════════════════════════════════════════════════════════════════


def _normalize_date(raw: str) -> str:
    """Normalize QIF dates to MM/DD/YYYY.

    Handles:
      - MM/DD/YYYY   (standard): pass through
      - MM/DD'YY     (apostrophe): convert 'YY → /20YY
      - M/D'YY, M/DD'YY, MM/D'YY (space or no-space padding)
    """
    raw = raw.strip()

    # Already MM/DD/YYYY format
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", raw):
        parts = raw.split("/")
        return f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"

    # MM/DD'YY or M/D'YY format
    m = re.match(r"^(\d{1,2})\s*/\s*(\d{1,2})\s*'(\d{2})$", raw)
    if m:
        month = m.group(1).zfill(2)
        day = m.group(2).zfill(2)
        year = "20" + m.group(3)
        return f"{month}/{day}/{year}"

    return raw  # fall through unchanged


# ═══════════════════════════════════════════════════════════════════
#  Amount helpers
# ═══════════════════════════════════════════════════════════════════


def _clean_amount(raw: str) -> str:
    """Strip currency symbols, commas, and normalize decimal."""
    s = raw.replace("$", "").replace(",", "").strip()
    if "." not in s:
        s += ".00"
    return s


# ═══════════════════════════════════════════════════════════════════
#  Main parser
# ═══════════════════════════════════════════════════════════════════


def _flush_record(records: list[QIFRecord], current: QIFRecord | None
                  ) -> QIFRecord | None:
    """Append *current* to *records* and return ``None``."""
    if current is not None:
        records.append(current)
    return None


def parse_qif(text: str) -> list[QIFRecord]:
    """Parse QIF text into a list of :class:`QIFRecord`.

    Only returns records from transaction-producing sections
    (Bank, CCard, Cash, Invst). All other sections are ignored.

    Args:
        text: Raw QIF file contents (may contain \\r\\n line endings).

    Returns:
        List of QIFRecord instances.
    """
    records: list[QIFRecord] = []
    current: QIFRecord | None = None
    acct_type = ""
    in_transaction_section = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")

        if not line:
            continue

        # ── Section headers ──────────────────────────────────
        if line.startswith("!"):

            # !Option → skip entirely (may be followed by !Type:Xxx)
            if line.startswith("!Option"):
                in_transaction_section = False
                current = None
                continue

            # !Type:Xxx → determine if this produces CSV rows
            if line.startswith("!Type:"):
                section = line[6:].strip().lower()
                in_transaction_section = section in TRANSACTION_TYPES
                if in_transaction_section:
                    # Normalize section names for output
                    acct_type = section.capitalize()
                    if acct_type == "Ccard":
                        acct_type = "CCard"
                else:
                    acct_type = ""
                    current = None
                continue

            # Any other !XXXX → skip
            in_transaction_section = False
            current = None
            continue

        # ── Skip non-transaction sections ────────────────────
        if not in_transaction_section:
            continue

        # ── End of entry: "^\n" or "^MoreContent" ───────────
        # The ^ may be followed immediately by another section
        # header on the same line (e.g. "^!Type:Invst").
        if line[0] == "^":
            current = _flush_record(records, current)
            remainder = line[1:].strip()
            if remainder.startswith("!"):
                # Re-process the remainder as a new section header
                # by feeding it through the loop again via continue,
                # but we need to handle it here directly.
                if remainder.startswith("!Type:"):
                    section = remainder[6:].strip().lower()
                    in_transaction_section = section in TRANSACTION_TYPES
                    if in_transaction_section:
                        acct_type = section.capitalize()
                        if acct_type == "Ccard":
                            acct_type = "CCard"
                    else:
                        acct_type = ""
                    continue
                else:
                    in_transaction_section = False
                    continue
            # Otherwise, remainder is a subtitle/comment — skip it
            continue

        # ── Start a new record if needed ─────────────────────
        if current is None:
            current = QIFRecord(acct_type=acct_type)

        code = line[0]
        value = line[1:].strip()

        if code == "D":
            current.date = _normalize_date(value)
        elif code == "T":
            current.amount = _clean_amount(value)
        elif code == "U":
            if not current.amount:
                current.amount = _clean_amount(value)
        elif code == "P":
            current.payee = value
        elif code == "M":
            current.memo = value
        elif code == "L":
            current.category = value
        elif code == "N":
            current.check_num = value
        elif code == "C":
            current.cleared = value
        elif code == "R":
            if not current.cleared:
                current.cleared = value
        elif code == "Y":
            current.ticker = value
        elif code == "I":
            try:
                current.price = float(value.replace(",", ""))
            except ValueError:
                pass
        elif code == "Q":
            try:
                current.quantity = float(value.replace(",", ""))
            except ValueError:
                pass
        # Fields we don't store
        elif code in ("$", "%"):
            pass
        # Any other code is ignored

    # Post-process: infer payee for investment records that lack a P field
    for r in records:
        if not r.payee and r.check_num and r.acct_type.lower() == "invst":
            action = r.check_num
            if r.ticker:
                r.payee = f"{action} {r.ticker}"
            else:
                r.payee = action

    return records


# ═══════════════════════════════════════════════════════════════════
#  Price section parser (also used by import_529.py)
# ═══════════════════════════════════════════════════════════════════


def _parse_prices(text: str) -> list[tuple[str, int, str]]:
    """Parse !Type:Prices section from QIF text.

    Returns list of (ticker, price_cents, date_str) tuples.

    Price format::

        "TICKER",1877 3/4," 3/26'25"
        ^
    """
    results: list[tuple[str, int, str]] = []
    in_prices = False

    for line in text.splitlines():
        line = line.rstrip("\r").strip()
        if not line:
            continue
        # Handle ^!Type:Prices (same line, no newline) — must check BEFORE in_prices guard
        if line.startswith("^") and len(line) > 1:
            remainder = line[1:].strip()
            if remainder.startswith("!Type:Prices"):
                in_prices = True
                continue
            elif remainder.startswith("!"):
                in_prices = False
                continue

        if line == "!Type:Prices":
            in_prices = True
            continue
        if not in_prices:
            continue
        if line == "^":
            continue

        # Parse: "TICKER",price," date"
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 3:
            ticker = parts[0]
            raw_price = parts[1].strip()
            # Handle fraction prices like "1877 3/4"
            frac_parts = raw_price.split()
            if len(frac_parts) == 2 and "/" in frac_parts[1]:
                whole = float(frac_parts[0])
                num, den = frac_parts[1].split("/")
                price_dollars = whole + float(num) / float(den)
            else:
                try:
                    price_dollars = float(raw_price)
                except ValueError:
                    continue
            price_cents = int(round(price_dollars * 100))
            date_str = parts[2].strip()
            results.append((ticker, price_cents, date_str))

    return results

    # Don't forget the last record
    if current is not None:
        records.append(current)

    return records


# ═══════════════════════════════════════════════════════════════════
#  CSV converter
# ═══════════════════════════════════════════════════════════════════


def convert_qif(text: str) -> str:
    """Parse QIF text and return CSV as a string.

    Args:
        text: Raw QIF file contents.

    Returns:
        CSV-formatted string with header row, or empty string for
        empty/no-transaction input.
    """
    records = parse_qif(text)
    if not records:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Amount", "Payee", "Memo", "Category",
                      "Type", "CheckNum", "Cleared", "Ticker"])

    for r in records:
        writer.writerow([
            r.date,
            r.amount,
            r.payee,
            r.memo,
            r.category,
            r.acct_type,
            r.check_num,
            r.cleared,
            r.ticker,
        ])

    return output.getvalue()


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> None:
    """CLI entry point::

        python -m ledger.scripts.qif_to_csv data.qif > output.csv
        python -m ledger.scripts.qif_to_csv data.qif --output data.csv
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(0 if not argv else 1)

    input_path = argv[0]
    output_path = None

    if "--output" in argv:
        idx = argv.index("--output")
        output_path = argv[idx + 1]

    with open(input_path, encoding="utf-8") as f:
        csv_text = convert_qif(f.read())

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(csv_text)
        print(f"Wrote {output_path}", file=sys.stderr)
    else:
        sys.stdout.write(csv_text)


if __name__ == "__main__":
    main()
