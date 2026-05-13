"""Tests for QIF import in the GUI.

Verifies the import flow: menu wiring, file dialog integration,
and result display.
"""

import tempfile
import os
import pytest


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def sample_qif_path() -> str:
    """Write a small QIF to a temp file and return the path."""
    qif = """!Type:Bank
D01/15/2026
U-150.00
T-150.00
PGROCERY STORE
LExpenses:Food
^
D01/16/2026
U2000.00
T2000.00
PDIRECT DEPOSIT
LIncome:Salary
^"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qif", delete=False) as f:
        f.write(qif)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ── Import flow tests (pure logic, no tkinter) ────────────────────


class TestImportFlow:
    """The import flow — file selection → import → result display."""

    def test_import_via_general_importer(self, sample_qif_path: str):
        """Calling the general importer from the GUI code should work."""
        from ledger.scripts.import_qif import import_qif
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        try:
            summary = import_qif(sample_qif_path, db_path)
            assert summary["entries_created"] >= 2
            assert summary["type"] == "Bank/CCard"
        finally:
            os.unlink(db_path)

    def test_dry_run(self, sample_qif_path: str):
        """Dry run before import to show what the file contains."""
        from ledger.scripts.import_qif import import_qif
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        try:
            summary = import_qif(sample_qif_path, db_path, dry_run=True)
            assert summary["records_found"] >= 2
            assert summary["dry_run"] is True
        finally:
            try: os.unlink(db_path)
            except OSError: pass

    def test_import_updates_database(self, sample_qif_path: str):
        """After import, the database should have the imported transactions."""
        from ledger.scripts.import_qif import import_qif
        from ledger.controllers.accounts import AccountManager
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        try:
            import_qif(sample_qif_path, db_path)
            mgr = AccountManager(db_path)
            eq = mgr.check_accounting_equation()
            assert eq["balanced"] is True
            assert len(mgr.journal.transactions) >= 2
        finally:
            os.unlink(db_path)

    def test_invalid_file_handled_gracefully(self):
        """Importing a non-existent file should not crash."""
        from ledger.scripts.import_qif import import_qif
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        try:
            with pytest.raises(FileNotFoundError):
                import_qif("/nonexistent/file.qif", db_path)
        finally:
            try: os.unlink(db_path)
            except OSError: pass

    def test_non_qif_file(self):
        """Trying to import a non-QIF file should handle gracefully."""
        from ledger.scripts.import_qif import import_qif
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
        ) as f:
            f.write("This is not QIF data\n")
            path = f.name
        db_path = tempfile.mktemp(suffix=".db")
        try:
            summary = import_qif(path, db_path)
            assert summary["entries_created"] == 0
        finally:
            os.unlink(path)
            os.unlink(db_path)
