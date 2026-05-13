"""Component tests: PySide6 — reports — report viewer functions.

Tests the capture hook and formatted output of each report function.
UI-agnostic — no PySide6 widgets needed for the capture path.
"""

from __future__ import annotations

import sys

import pytest

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False

import ledger.gui_pyside.reports as reports


@pytest.fixture(autouse=True)
def _capture(monkeypatch):
    """Install ``_captured_reports`` list before each test, clear after."""
    mod = sys.modules["ledger.gui_pyside.reports"]
    storage: list[tuple[str, str]] = []
    setattr(mod, "_captured_reports", storage)
    yield storage
    setattr(mod, "_captured_reports", None)


class TestShowTextCapture:
    """The ``_captured_reports`` hook intercepts _show_text calls."""

    def test_capture_appends(self, _capture):
        reports._show_text(None, "Test Title", "Hello, World!")
        assert len(_capture) == 1
        title, text = _capture[0]
        assert title == "Test Title"
        assert "Hello, World!" in text

    def test_multiple_captures(self, _capture):
        reports._show_text(None, "A", "First")
        reports._show_text(None, "B", "Second")
        assert len(_capture) == 2
        assert _capture[0][0] == "A"
        assert _capture[1][0] == "B"


class TestShowNetWorth:
    """Net worth report captures correctly."""

    def test_contains_keys(self, fast_seeded, _capture):
        reports.show_net_worth(None, fast_seeded)
        _, text = _capture[0]
        assert "Assets:" in text
        assert "Liabilities:" in text
        assert "Net Worth:" in text

    def test_format_is_usd(self, fast_seeded, _capture):
        reports.show_net_worth(None, fast_seeded)
        import re
        _, text = _capture[0]
        amounts = re.findall(r"\$[\d,]+\.\d{2}", text)
        assert len(amounts) >= 4


class TestShowSummary:
    def test_contains_groups(self, fast_seeded, _capture):
        reports.show_summary(None, fast_seeded)
        _, text = _capture[0]
        for group in ["ASSETS", "LIABILITIES", "EQUITY", "INCOME", "EXPENSES"]:
            assert group in text.upper()

    def test_contains_net_worth(self, fast_seeded, _capture):
        reports.show_summary(None, fast_seeded)
        _, text = _capture[0]
        assert "Net Worth:" in text

    def test_balanced_summary(self, fast_seeded, _capture):
        reports.show_summary(None, fast_seeded)
        _, text = _capture[0]
        assert "Balanced" in text


class TestShowIncomeStmt:
    def test_contains_title(self, fast_seeded, _capture):
        reports.show_income_stmt(None, fast_seeded)
        _, text = _capture[0]
        assert "Income Statement" in text

    def test_net_income_matches_backend(self, fast_seeded, _capture):
        backend_ni = fast_seeded.gen_income_report()["net_income"]
        reports.show_income_stmt(None, fast_seeded)
        _, text = _capture[0]
        import re
        match = re.search(r"(Net Income|Net Loss):\s*([-\$0-9,\.]+)", text)
        assert match is not None
        raw = match.group(2).replace("$", "").replace(",", "")
        val = int(round(float(raw) * 100))
        assert val == backend_ni


class TestShowBalanceSheet:
    def test_contains_sections(self, fast_seeded, _capture):
        reports.show_balance_sheet(None, fast_seeded)
        _, text = _capture[0]
        assert "ASSETS" in text
        assert "LIABILITIES" in text
        assert "EQUITY" in text

    def test_balanced_status(self, fast_seeded, _capture):
        reports.show_balance_sheet(None, fast_seeded)
        _, text = _capture[0]
        assert "Balanced" in text


class TestShowReStatement:
    def test_contains_sections(self, fast_seeded, _capture):
        reports.show_re_statement(None, fast_seeded)
        _, text = _capture[0]
        assert "Beginning RE" in text
        assert "Net Income" in text
        assert "Ending RE" in text


class TestShowAbout:
    def test_contains_app_name(self, _capture):
        reports.show_about(None)
        _, text = _capture[0]
        assert "Double-Entry Accounting" in text
