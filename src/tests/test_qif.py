"""Tests for QIF → CSV converter.

The converter parses QIF (Quicken Interchange Format) files and
outputs clean CSV with rows for every transaction.
"""

import csv
import io
import tempfile
import os
import pytest

from ledger.scripts.qif_to_csv import convert_qif, parse_qif, QIFRecord


# ═══════════════════════════════════════════════════════════════════
#  parse_qif tests
# ═══════════════════════════════════════════════════════════════════


SAMPLE_BANK_QIF = """!Type:Bank
D01/15/2026
T-150.00
PGROCERY STORE
MWeekly shopping
LExpenses:Food
^
D01/16/2026
T2000.00
PDIRECT DEPOSIT
LAcme Corp
CPayroll
^
D01/20/2026
T-45.50
PAMAZON.COM
MBooks
LExpenses:Entertainment
^"""

SAMPLE_CC_QIF = """!Type:CCard
D02/01/2026
T-500.00
PBEST BUY
MElectronics
LExpenses:Shopping
^
D02/05/2026
T-32.99
PNETFLIX
MSubscription
LExpenses:Entertainment
^"""


class TestParseQIF:
    """Parsing raw QIF text into structured records."""

    def test_basic_bank_file(self):
        records = list(parse_qif(SAMPLE_BANK_QIF))
        assert len(records) == 3

    def test_basic_credit_card_file(self):
        records = list(parse_qif(SAMPLE_CC_QIF))
        assert len(records) == 2

    def test_record_fields(self):
        records = list(parse_qif(SAMPLE_BANK_QIF))
        r = records[0]
        assert r.date == "01/15/2026"
        assert r.amount == "-150.00"
        assert r.payee == "GROCERY STORE"
        assert r.memo == "Weekly shopping"
        assert r.category == "Expenses:Food"

    def test_second_record(self):
        records = list(parse_qif(SAMPLE_BANK_QIF))
        r = records[1]
        assert r.date == "01/16/2026"
        assert r.amount == "2000.00"
        assert r.payee == "DIRECT DEPOSIT"

    def test_detect_type(self):
        records = list(parse_qif(SAMPLE_BANK_QIF))
        assert records[0].acct_type == "Bank"

    def test_cc_type(self):
        records = list(parse_qif(SAMPLE_CC_QIF))
        assert records[0].acct_type == "CCard"

    def test_empty_returns_no_records(self):
        records = list(parse_qif(""))
        assert records == []

    def test_header_only_no_entries(self):
        records = list(parse_qif("!Type:Bank\n^\n"))
        assert len(records) == 0

    def test_missing_end_marker(self):
        """Records without a '^' end marker should still be yielded."""
        text = "!Type:Bank\nD01/01/2026\nT-100.00\nPTest\n"
        records = list(parse_qif(text))
        assert len(records) == 1

    def test_investment_qif(self):
        """Investment QIF files have different fields — should still parse basic info."""
        invest = """!Type:Invst
D01/10/2026
NBuy
YVTI
I275.00
Q100
T-27500.00
MBought 100 shares VTI
^"""
        records = list(parse_qif(invest))
        assert len(records) == 1
        r = records[0]
        assert r.date == "01/10/2026"
        assert r.amount == "-27500.00"
        assert r.memo == "Bought 100 shares VTI"
        assert r.payee == "Buy VTI"  # N=action, Y=ticker → combined

    def test_memo_fallback_to_payee(self):
        """If no memo (M field), use P as both payee and memo."""
        qif = "!Type:Bank\nD01/01/2026\nT-50.00\nPGAS STATION\n^"
        records = list(parse_qif(qif))
        assert records[0].payee == "GAS STATION"
        assert records[0].memo == ""  # no memo field

    def test_cleared_flag(self):
        qif = "!Type:Bank\nD01/01/2026\nT-50.00\nPGAS\nC*\n^"
        records = list(parse_qif(qif))
        assert records[0].cleared == "*"

    def test_check_number(self):
        qif = "!Type:Bank\nD01/01/2026\nT-50.00\nPGAS\nN1001\n^"
        records = list(parse_qif(qif))
        assert records[0].check_num == "1001"

    def test_special_chars_in_payee(self):
        qif = "!Type:Bank\nD01/01/2026\nT-10.00\nP7-ELEVEN #123\n^"
        records = list(parse_qif(qif))
        assert records[0].payee == "7-ELEVEN #123"


class TestParseQIFEdgeCases:
    """Edge cases and malformed QIF input."""

    def test_unicode_in_payee(self):
        qif = "!Type:Bank\nD01/01/2026\nT-50.00\nPCafé München 🥨\n^"
        records = list(parse_qif(qif))
        assert "Café" in records[0].payee

    def test_multiple_end_markers(self):
        qif = "!Type:Bank\nD01/01/2026\nT-50.00\nPTest\n^\n^\n^"
        records = list(parse_qif(qif))
        assert len(records) == 1

    def test_no_header(self):
        """QIF without a !Type header should still parse individual records."""
        qif = "D01/01/2026\nT-50.00\nPTest\n^\nD01/02/2026\nT100.00\nPTest2\n^"
        records = list(parse_qif(qif))
        assert len(records) == 2
        assert records[0].acct_type == ""

    def test_amount_with_currency_symbol(self):
        """Some QIF exports include $ in amounts — should strip it."""
        qif = "!Type:Bank\nD01/01/2026\nT-$150.00\nPGROCERY\n^"
        records = list(parse_qif(qif))
        assert records[0].amount == "-150.00"

    def test_amount_no_decimal(self):
        qif = "!Type:Bank\nD01/01/2026\nT-10000\nPGROCERY\n^"
        records = list(parse_qif(qif))
        assert records[0].amount == "-10000.00"

    def test_negative_positive_consistency(self):
        qif = "!Type:Bank\nD01/01/2026\nT150.00\nPPAYCHECK\n^"
        records = list(parse_qif(qif))
        assert records[0].amount == "150.00"


# ═══════════════════════════════════════════════════════════════════
#  convert_qif (file → CSV) tests
# ═══════════════════════════════════════════════════════════════════


class TestConvertQIF:
    """Integration: QIF file in → CSV string out."""

    def test_csv_header(self):
        csv_out = convert_qif(SAMPLE_BANK_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        expected = {"Date", "Amount", "Payee", "Memo", "Category", "Type", "CheckNum", "Cleared", "Ticker"}
        assert set(reader.fieldnames) == expected, f"Got {reader.fieldnames}"

    def test_csv_row_count(self):
        csv_out = convert_qif(SAMPLE_BANK_QIF)
        lines = csv_out.strip().split("\n")
        assert len(lines) == 4  # header + 3 data rows

    def test_csv_data(self):
        csv_out = convert_qif(SAMPLE_BANK_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        rows = list(reader)
        assert rows[0]["Date"] == "01/15/2026"
        assert rows[0]["Amount"] == "-150.00"
        assert rows[0]["Payee"] == "GROCERY STORE"
        assert rows[0]["Memo"] == "Weekly shopping"
        assert rows[0]["Category"] == "Expenses:Food"

    def test_empty_input(self):
        csv_out = convert_qif("")
        assert csv_out.strip() == ""

    def test_round_trip_file(self):
        """Write QIF to temp file, convert, verify output."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(SAMPLE_BANK_QIF)
            qif_path = f.name

        try:
            with open(qif_path) as f:
                csv_out = convert_qif(f.read())
            reader = csv.DictReader(io.StringIO(csv_out))
            rows = list(reader)
            assert len(rows) == 3
        finally:
            os.unlink(qif_path)

    def test_convert_cc_file(self):
        csv_out = convert_qif(SAMPLE_CC_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["Type"] == "CCard"
