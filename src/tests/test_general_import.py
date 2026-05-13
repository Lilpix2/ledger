"""Tests for the general QIF importer (handles all QIF types)."""
import tempfile, os, pytest
from ledger.controllers.accounts import AccountManager
from ledger.scripts.import_qif import import_qif

QIF_BANK = """!Type:Bank
D1/15'26
U-150.50
T-150.50
C*
PGROCERY STORE
LExpenses:Food
^
D1/16'26
U2000.00
T2000.00
CX
PDIRECT DEPOSIT
LIncome:Salary
^"""

QIF_CCARD = """!Type:CCard
D2/1'26
U-500.00
T-500.00
C*
PBEST BUY
LExpenses:Shopping
^"""

QIF_INVST_CASH = """!Type:Invst
D4/6'25
N Cash
U4150.00
T4150.00
L[Alex Brokerage XX2580]
MElectronic funds transfer received
^
D4/7'25
NDiv
YVTI
U12.50
T12.50
MDividend received
^
D4/8'25
NReinvDiv
YVTI
I275.00
Q0.0454
U12.50
T12.50
MDividend reinvested
^"""

QIF_MIXED = QIF_BANK + QIF_CCARD


class TestGeneralImporter:
    def test_import_bank(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(QIF_BANK); path = f.name
        try:
            s = import_qif(path, db_path)
            assert s["entries_created"] >= 2
            mgr = AccountManager(db_path)
            assert len(mgr.journal.transactions) >= 2
        finally:
            os.unlink(path)

    def test_import_ccard(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(QIF_CCARD); path = f.name
        try:
            s = import_qif(path, db_path)
            assert s["entries_created"] >= 1
        finally:
            os.unlink(path)

    def test_import_invst_cash(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(QIF_INVST_CASH); path = f.name
        try:
            s = import_qif(path, db_path)
            assert s["entries_created"] >= 1
        finally:
            os.unlink(path)

    def test_import_mixed(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(QIF_MIXED); path = f.name
        try:
            s = import_qif(path, db_path)
            assert s["entries_created"] >= 3
            mgr = AccountManager(db_path)
            eq = mgr.check_accounting_equation()
            assert eq["balanced"]
        finally:
            os.unlink(path)

    def test_dry_run(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(QIF_BANK); path = f.name
        try:
            s = import_qif(path, db_path, dry_run=True)
            assert s["dry_run"] is True
            assert s["records_found"] >= 2
        finally:
            os.unlink(path)

    def test_empty_qif(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write("!Type:Bank\n^\n"); path = f.name
        try:
            s = import_qif(path, db_path)
            assert s["entries_created"] == 0
        finally:
            os.unlink(path)

    def test_invst_cash_sets_balance(self, db_path):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
            f.write(QIF_INVST_CASH); path = f.name
        try:
            s = import_qif(path, db_path)
            mgr = AccountManager(db_path)
            eq = mgr.check_accounting_equation()
            assert eq["balanced"]
        finally:
            os.unlink(path)


@pytest.fixture
def db_path():
    path = tempfile.mktemp(suffix=".db")
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass
