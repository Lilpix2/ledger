"""Tests for importing 529 (MESP) QIF data into the ledger."""

import tempfile
import os
import pytest

from ledger.controllers.accounts import AccountManager
from ledger.scripts.import_529 import import_529
from ledger.scripts.qif_to_csv import _parse_prices


SAMPLE_QIF = """!Type:Invst
D05/16/2017
NBuyX
YMESP 13-14 Fund
I13.96
Q39.398281
CR
U550.00
T550.00
L[CFCU Checking]
$550.00
^
D06/15/2020
NBuyX
YMESP 22/23 Option
I11.75
Q46.808511
U550.00
T550.00
L[CFCU Checking]
$550.00
^
D12/31/2020
NShrsIn
YMESP 22/23 Option
I12.00
Q8.333333
T100.00
PDividend Reinvestment
^
D03/20/2019
NShrsOut
YMESP 13-14 Fund
PShrsOut MESP 13-14 Fund
MFund Conversion
R
^
D05/28/2021
NSellX
YMESP 22/23 Option
I13.056206
Q30.000
T391.69
PSellX MESP 22/23 Option
MBerkeley Summer Program
^"""

SAMPLE_PRICES = """!Type:Prices
"MESP 13-14 Fund",13.96," 5/16'17"
^
"MESP 13-14 Fund",15.25,"12/31'17"
^
"MESP 22/23 Option",12.50," 5/28'21"
^"""


@pytest.fixture
def qif_path() -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
        f.write(SAMPLE_QIF + SAMPLE_PRICES)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def db_path() -> str:
    path = tempfile.mktemp(suffix=".db")
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


class TestParsePrice:
    def test_simple_decimal(self):
        prices = _parse_prices(SAMPLE_PRICES)
        assert len(prices) == 3

    def test_empty_prices_section(self):
        assert _parse_prices("!Type:Prices\n^\n") == []

    def test_no_prices_section(self):
        assert _parse_prices("!Type:Invst\n^\n") == []


class TestImport529:

    def test_import_creates_entries(self, qif_path: str, db_path: str):
        summary = import_529(qif_path, db_path, dry_run=False)
        assert summary["entries_created"] >= 1

    def test_import_creates_accounts(self, qif_path: str, db_path: str):
        import_529(qif_path, db_path)
        mgr = AccountManager(db_path)
        names = {acct.name for acct in mgr.accounts.values()}
        assert "529 Plans" in names
        # MESP 13-14 Fund was closed via rollover — not in active accounts
        # Only funds with shares > 0 get accounts

    def test_import_keeps_equation_balanced(self, qif_path: str, db_path: str):
        import_529(qif_path, db_path)
        mgr = AccountManager(db_path)
        eq = mgr.check_accounting_equation()
        assert eq["balanced"] is True
        assert eq["net_worth"] > 0

    def test_import_prices(self, qif_path: str, db_path: str):
        import_529(qif_path, db_path)
        mgr = AccountManager(db_path)
        price = mgr.get_latest_price("MESP 13-14 Fund")
        assert price == 1525, f"Expected 1525, got {price}"

    def test_dry_run(self, qif_path: str, db_path: str):
        summary = import_529(qif_path, db_path, dry_run=True)
        assert summary["entries_created"] == 0
        mgr = AccountManager(db_path)
        assert len(mgr.journal.transactions) == 0

    def test_dry_run_no_db_write(self, qif_path: str, db_path: str):
        import_529(qif_path, db_path, dry_run=True)
        mgr = AccountManager(db_path)
        assert len(mgr.journal.transactions) == 0

    def test_import_empty_qif(self, db_path: str):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".qif", delete=False,
        ) as f:
            f.write("!Type:Invst\n^\n")
            path = f.name
        try:
            summary = import_529(path, db_path, dry_run=False)
            assert summary["entries_created"] == 0
        finally:
            os.unlink(path)

    def test_import_twice_idempotent(self, qif_path: str, db_path: str):
        import_529(qif_path, db_path)
        import_529(qif_path, db_path)
        mgr = AccountManager(db_path)
        eq = mgr.check_accounting_equation()
        assert eq["balanced"] is True

    def test_prices_persist(self, qif_path: str, db_path: str):
        import_529(qif_path, db_path)
        mgr = AccountManager(db_path)
        price = mgr.get_latest_price("MESP 13-14 Fund")
        assert price == 1525
