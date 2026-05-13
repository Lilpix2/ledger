"""
Tests for QIF → CSV converter — revised to handle all real-world QIF variants.

From studying actual QIF files (gnucash export, 529 export, MESP invest):
  - Bank/CCard: N=payee (gnucash puts account names here), D=date MM/DD/YYYY
  - Invst: N=action (Buy/Sell), Y=ticker, I=price, Q=quantity, T=amount, D=date
  - Invst date: can be MM/DD'YY (apostrophe) or MM/DD/YYYY
  - Security: definitions only — skip
  - Prices: CSV-style — skip
  - Account: definitions — skip
  - Oth L, Option:AM, QIF header — skip
"""

import csv
import io
import os
import tempfile
import pytest

from ledger.scripts.qif_to_csv import convert_qif


# ═══════════════════════════════════════════════════════════════════
#  Section: what to include / skip
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
LIncome:Salary
C*
^"""

SAMPLE_CC_QIF = """!Type:CCard
D02/01/2026
T-500.00
PBEST BUY
MElectronics
LExpenses:Shopping
^"""

SAMPLE_INVST_QIF = """!Type:Invst
D01/15/2021
NBuy
YMESP 22/23 Option
I10.930004
Q50.3202
T550.00
P22/23 Option
^
D01/16/2023
NSell
YMESP 22/23 Option
I10.839999
Q-232.3063
T2518.20
P22/23 Option
^"""

# 529 export uses apostrophe-date format
SAMPLE_INVST_APOSTROPHE = """!Type:Invst
D5/16'17
NBuyX
YMESP 13-14 Fund
I13.96
Q39.398281
CR
U550.00
T550.00
L[CFCU Checking]
$550.00
^"""


class TestSectionFiltering:
    """Only Bank, CCard, Cash, Invst sections produce CSV rows."""

    def test_bank_yields_rows(self):
        csv_out = convert_qif(SAMPLE_BANK_QIF)
        assert len(csv_out.strip().split("\n")) == 3  # header + 2 rows

    def test_ccard_yields_rows(self):
        csv_out = convert_qif(SAMPLE_CC_QIF)
        assert len(csv_out.strip().split("\n")) == 2  # header + 1 row

    def test_invst_yields_rows(self):
        csv_out = convert_qif(SAMPLE_INVST_QIF)
        assert len(csv_out.strip().split("\n")) == 3  # header + 2 rows

    def test_invst_apostrophe_date(self):
        csv_out = convert_qif(SAMPLE_INVST_APOSTROPHE)
        reader = csv.DictReader(io.StringIO(csv_out))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Date"] == "05/16/2017"

    def test_security_section_skipped(self):
        qif = """!Type:Security
N1ST CTZNS BNCSHS INC A
SFCNCA
TStock
^
"""
        csv_out = convert_qif(qif)
        assert csv_out.strip() == ""

    def test_prices_section_skipped(self):
        qif = """!Type:Prices
"FCNCA",1877 3/4," 3/26'25"
^
"""
        csv_out = convert_qif(qif)
        assert csv_out.strip() == ""

    def test_account_section_skipped(self):
        qif = """!Account
NCurrent Assets
TBank
D:\n^"""
        csv_out = convert_qif(qif)
        assert csv_out.strip() == ""

    def test_oth_l_skipped(self):
        qif = "!Type:Oth L\n^Alex Brokerage XX2580\n^\n"
        csv_out = convert_qif(qif)
        assert csv_out.strip() == ""

    def test_option_am_skipped(self):
        qif = "!Option:AM\n!Type:Bank\nD01/01/2026\nT-50.00\nPTest\n^\n"
        csv_out = convert_qif(qif)
        # !Option:AM is skipped, !Type:Bank should still be parsed
        assert "$50.00" in csv_out or "-50.00" in csv_out

    def test_qif_header_skipped(self):
        qif = "!Type:QIF\n"
        csv_out = convert_qif(qif)
        assert csv_out.strip() == ""

    def test_mixed_sections(self):
        """Bank + Security + Invst mixed — only Bank and Invst produce rows."""
        qif = (
            "!Type:Security\nNTest\nSTEST\nTStock\n^\n"
            + SAMPLE_BANK_QIF
            + SAMPLE_INVST_QIF
        )
        csv_out = convert_qif(qif)
        reader = csv.DictReader(io.StringIO(csv_out))
        rows = list(reader)
        assert len(rows) == 4  # 2 bank + 2 invst


# ═══════════════════════════════════════════════════════════════════
#  Date parsing
# ═══════════════════════════════════════════════════════════════════


class TestDateParsing:
    """Handle MM/DD/YYYY, MM/DD'YY, and space-padded variants."""

    def test_standard_date(self):
        csv_out = convert_qif("!Type:Bank\nD12/25/2026\nT-10.00\nPXmas\n^\n")
        assert "12/25/2026" in csv_out

    def test_apostrophe_date(self):
        csv_out = convert_qif("!Type:Invst\nD5/16'17\nNBuy\nYTicker\nT-100.00\n^\n")
        assert "05/16/2017" in csv_out

    def test_apostrophe_date_january(self):
        csv_out = convert_qif("!Type:Invst\nD1/ 1'20\nNBuy\nYTicker\nT-100.00\n^\n")
        assert "01/01/2020" in csv_out

    def test_apostrophe_date_dec(self):
        csv_out = convert_qif("!Type:Invst\nD12/25'25\nNBuy\nYTicker\nT-100.00\n^\n")
        assert "12/25/2025" in csv_out

    def test_no_date_invst_uses_empty(self):
        csv_out = convert_qif("!Type:Invst\nNBuy\nYTicker\nT-100.00\n^\n")
        assert "Buy" in csv_out  # shouldn't crash

    def test_bad_date_falls_through(self):
        csv_out = convert_qif("!Type:Bank\nDnot-a-date\nT-10.00\nPTest\n^\n")
        assert "not-a-date" in csv_out


# ═══════════════════════════════════════════════════════════════════
#  Investment transaction fields
# ═══════════════════════════════════════════════════════════════════


class TestInvstFields:
    """Investment-specific QIF fields: N, Y, I, Q, U, C, R."""

    def test_buy_fields(self):
        csv_out = convert_qif("!Type:Invst\nD01/15/2021\nNBuy\nYMESP\nI10.93\nQ50.32\nT550.00\nP22/23 Option\n^\n")
        reader = csv.DictReader(io.StringIO(csv_out))
        r = list(reader)[0]
        assert r["Payee"] == "22/23 Option"
        assert r["Amount"] == "550.00"
        assert r["Ticker"] == "MESP"

    def test_sell_fields(self):
        csv_out = convert_qif("!Type:Invst\nD01/16/2023\nNSell\nYMESP\nI10.84\nQ-232.31\nT2518.20\nP22/23 Option\n^\n")
        reader = csv.DictReader(io.StringIO(csv_out))
        r = list(reader)[0]
        assert r["Amount"] == "2518.20"
        assert r["Ticker"] == "MESP"

    def test_buyx_action(self):
        """NBuyX is valid action (used by 529 export)."""
        csv_out = convert_qif("!Type:Invst\nD5/16'17\nNBuyX\nYMESP 13-14 Fund\nI13.96\nQ39.40\nT550.00\n^\n")
        reader = csv.DictReader(io.StringIO(csv_out))
        r = list(reader)[0]
        assert r["Payee"] == "BuyX MESP 13-14 Fund"  # inferred from action + ticker

    def test_invst_with_u_field(self):
        """U field = user-entered amount (before rounding)."""
        csv_out = convert_qif("!Type:Invst\nD01/01/2026\nNBuy\nYTicker\nU550.00\nT550.00\n^\n")
        assert "550.00" in csv_out

    def test_invst_no_payee_inferred(self):
        """When no P field, infer Payee from N action + Y ticker."""
        csv_out = convert_qif("!Type:Invst\nD01/01/2026\nNBuy\nYVTI\nI275.00\nQ100\nT-27500.00\n^\n")
        reader = csv.DictReader(io.StringIO(csv_out))
        r = list(reader)[0]
        assert r["Payee"] == "Buy VTI"

    def test_invst_with_memo(self):
        csv_out = convert_qif("!Type:Invst\nD01/01/2026\nNBuy\nYVTI\nMQuarterly purchase\nT-27500.00\n^\n")
        reader = csv.DictReader(io.StringIO(csv_out))
        r = list(reader)[0]
        assert r["Memo"] == "Quarterly purchase"


# ═══════════════════════════════════════════════════════════════════
#  Bank/CCard edge cases
# ═══════════════════════════════════════════════════════════════════


class TestBankCCard:
    """Standard bank/credit-card transaction parsing."""

    def test_header_with_subtitle(self):
        """Some QIF files have a subtitle line right after the !Type header."""
        qif = "!Type:Bank\n^My Account\nD01/01/2026\nT-10.00\nPTest\n^\n"
        csv_out = convert_qif(qif)
        assert "10.00" in csv_out

    def test_crlf_line_endings(self):
        """QIF files may have \\r\\n (Windows) line endings."""
        qif = "!Type:Bank\r\nD01/01/2026\r\nT-10.00\r\nPTest\r\n^\r\n"
        csv_out = convert_qif(qif)
        assert "10.00" in csv_out

    def test_empty_memo(self):
        qif = "!Type:Bank\nD01/01/2026\nT-5.00\nPStore\n^\n"
        csv_out = convert_qif(qif)
        reader = csv.DictReader(io.StringIO(csv_out))
        assert list(reader)[0]["Memo"] == ""

    def test_memo_fallback(self):
        """When only one of P/M is present, the other should be empty."""
        qif = "!Type:Bank\nD01/01/2026\nT-5.00\nPStore\n^\n"
        csv_out = convert_qif(qif)
        reader = csv.DictReader(io.StringIO(csv_out))
        r = list(reader)[0]
        assert r["Payee"] == "Store"
        assert r["Memo"] == ""
        assert r["Category"] == ""


# ═══════════════════════════════════════════════════════════════════
#  CSV output format
# ═══════════════════════════════════════════════════════════════════


class TestCSVOutput:
    """The CSV should have a consistent, predictable format."""

    def test_header_columns(self):
        csv_out = convert_qif(SAMPLE_BANK_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        expected = {"Date", "Amount", "Payee", "Memo", "Category", "Type", "CheckNum", "Cleared", "Ticker"}
        assert set(reader.fieldnames) == expected

    def test_type_column(self):
        csv_out = convert_qif(SAMPLE_CC_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        assert list(reader)[0]["Type"] == "CCard"

    def test_bank_type(self):
        csv_out = convert_qif(SAMPLE_BANK_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        assert list(reader)[0]["Type"] == "Bank"

    def test_invst_type(self):
        csv_out = convert_qif(SAMPLE_INVST_QIF)
        reader = csv.DictReader(io.StringIO(csv_out))
        assert list(reader)[0]["Type"] == "Invst"

    def test_empty_input_returns_empty(self):
        assert convert_qif("").strip() == ""

    def test_no_transactions_returns_empty(self):
        """File with headers but no transaction records."""
        qif = "!Type:BanK\n^\n!Type:Security\nNTest\nSTEST\nTStock\n^\n"
        assert convert_qif(qif).strip() == ""


# ═══════════════════════════════════════════════════════════════════
#  File round-trip
# ═══════════════════════════════════════════════════════════════════


class TestFileRoundtrip:
    """Reading QIF from file produces correct CSV."""

    def test_round_trip(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(SAMPLE_BANK_QIF)
            f.write(SAMPLE_INVST_QIF)
            path = f.name
        try:
            from ledger.scripts.qif_to_csv import main
            # Capture stdout
            import sys
            from io import StringIO
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            try:
                main([path])
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            reader = csv.DictReader(io.StringIO(output))
            rows = list(reader)
            assert len(rows) == 4  # 2 bank + 2 invst
        finally:
            os.unlink(path)

    def test_cli_with_output_flag(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(SAMPLE_BANK_QIF)
            qif_path = f.name
        csv_path = qif_path + ".csv"
        try:
            from ledger.scripts.qif_to_csv import main
            main([qif_path, "--output", csv_path])
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 2
        finally:
            os.unlink(qif_path)
            if os.path.exists(csv_path):
                os.unlink(csv_path)
