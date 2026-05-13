"""
QIF → CSV converter.

Parses QIF (Quicken Interchange Format) files and outputs clean CSV
with one row per transaction.

Usage::

    python -m ledger.scripts.qif_to_csv input.qif > output.csv
    python -m ledger.scripts.qif_to_csv input.qif --output output.csv

QIF format reference:
    !Type:<type>       — section header (Bank, CCard, Invst, Cash, …)
    D<date>            — date
    T<amount>          — amount (positive=inflow, negative=outflow)
    P<payee>           — payee / description
    M<memo>            — memo (longer description)
    L<category>        — category / account
    N<check|action>    — check number (Bank) or action (Invst: Buy/Sell)
    Y<ticker>          — ticker symbol (Invst)
    I<price>           — price per share (Invst)
    Q<quantity>        — shares (Invst)
    C<status>          — cleared status (*, c, or blank)
    ^                  — end of entry
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from dataclasses import dataclass, field
from typing import TextIO


# ── QIF Record ─────────────────────────────────────────────────────


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
    ticker: str = ""  # Investment ticker (Y field)


# ── Parser ─────────────────────────────────────────────────────────


def _clean_amount(raw: str) -> str:
    """Strip currency symbols and normalize decimal format.

    >>> _clean_amount("-$150.00")
    '-150.00'
    >>> _clean_amount("10000")
    '10000.00'
    >>> _clean_amount("$1,234.56")
    '1234.56'
    """
    s = raw.replace("$", "").replace(",", "").strip()
    # Add .00 if no decimal
    if "." not in s:
        s += ".00"
    return s


def parse_qif(text: str) -> list[QIFRecord]:
    """Parse QIF text into a list of :class:`QIFRecord`.

    Args:
        text: Raw QIF file contents.

    Returns:
        List of QIFRecord instances, one per transaction.
    """
    records: list[QIFRecord] = []
    current: QIFRecord | None = None
    acct_type = ""

    for line in text.splitlines():
        line = line.rstrip("\r")

        if not line:
            continue

        # Section header
        if line.startswith("!Type:"):
            acct_type = line[6:]
            continue

        # End of entry
        if line == "^":
            if current is not None:
                # Infer payee from investment action + ticker if no P field
                if not current.payee and current.check_num:
                    action = current.check_num
                    ticker = current.ticker
                    if ticker:
                        current.payee = f"{action} {ticker}"
                    else:
                        current.payee = action
                records.append(current)
                current = None
            continue

        # Skip header-only files (no records to parse)
        if current is None:
            current = QIFRecord(acct_type=acct_type)

        code = line[0]
        value = line[1:].strip()

        if code == "D":
            current.date = value
        elif code == "T":
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
        elif code == "Y":
            # Investment ticker — store separately
            current.ticker = value
        elif code == "I":
            # Price per share (investment) — not stored in output
            pass
        elif code == "Q":
            # Quantity (investment) — not stored in output
            pass

    # Don't forget the last record if it has no ^ terminator
    if current is not None:
        records.append(current)

    return records


# ── Converter ──────────────────────────────────────────────────────


def convert_qif(text: str) -> str:
    """Parse QIF text and return CSV as a string.

    Args:
        text: Raw QIF file contents.

    Returns:
        CSV-formatted string with header row.
    """
    records = parse_qif(text)
    if not records:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Amount", "Payee", "Memo", "Category", "Type", "CheckNum", "Cleared", "Ticker"])

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


# ── CLI Entry Point ────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """CLI entry point::

        python -m ledger.scripts.qif_to_csv data.qif > output.csv
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
