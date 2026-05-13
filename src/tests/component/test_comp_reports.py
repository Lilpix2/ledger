"""Component tests: ``gui/reports.py`` — report viewer functions.

Tests
-----
- ``_show_text`` — capture hook works without opening a dialog
- ``show_net_worth`` — formatted output contains expected values
- ``show_summary`` — group structure and balanced status
- ``show_income_stmt`` — income/expense breakdown
- ``show_balance_sheet`` — A = L + E format
- ``show_re_statement`` — RE rollforward
- ``show_about`` — static text display

Boundary
--------
Backend mocked via ``fast_manager`` / ``fast_seeded`` (MockDB).
Dialog capture via ``_captured_reports`` test hook — no tkinter needed.

Black-box
---------
Tests assert on the *text output* of each report function. No dialog
widget internals are inspected. Refactoring the formatting logic
should not break these tests.
"""

from __future__ import annotations

from unittest.mock import patch

import sys

import pytest

try:
    import ledger.gui.reports as reports
except ImportError:
    pytest.skip("tkinter not available (needed by gui package init)", allow_module_level=True)


# ═══════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _capture(monkeypatch, request):
    """Install ``_captured_reports`` list before each test, clear after.

    This hooks into ``_show_text`` which checks ``sys.modules`` for the
    attribute. When set, reports append (title, text) tuples instead of
    opening dialogs.
    """
    mod = sys.modules["ledger.gui.reports"]
    storage: list[tuple[str, str]] = []
    # Store on the module object (can't use monkeypatch.setattr for module
    # attrs directly, so use setattr on the module)
    setattr(mod, "_captured_reports", storage)
    yield storage
    setattr(mod, "_captured_reports", None)


# ═══════════════════════════════════════════════════════════════════
#  _show_text capture
# ═══════════════════════════════════════════════════════════════════


class TestShowTextCapture:
    """The ``_captured_reports`` hook intercepts _show_text calls."""

    def test_capture_appends(self, _capture):
        """Captured reports list grows when _show_text is called."""
        reports._show_text(None, "Test Title", "Hello, World!")
        assert len(_capture) == 1
        title, text = _capture[0]
        assert title == "Test Title"
        assert "Hello, World!" in text

    def test_multiple_captures(self, _capture):
        """Multiple calls append sequentially."""
        reports._show_text(None, "A", "First")
        reports._show_text(None, "B", "Second")
        assert len(_capture) == 2
        assert _capture[0][0] == "A"
        assert _capture[1][0] == "B"


# ═══════════════════════════════════════════════════════════════════
#  show_net_worth
# ═══════════════════════════════════════════════════════════════════


class TestShowNetWorth:
    """Net worth report captures correctly."""

    def test_contains_keys(self, fast_seeded, _capture):
        """Output includes Assets, Liabilities, Net Worth."""
        reports.show_net_worth(None, fast_seeded)
        assert len(_capture) == 1
        title, text = _capture[0]
        assert title == "Net Worth"
        assert "Assets:" in text
        assert "Liabilities:" in text
        assert "Net Worth:" in text
        assert "Equity:" in text

    def test_format_is_usd(self, fast_seeded, _capture):
        """Numeric values are formatted as $X,XXX.XX."""
        reports.show_net_worth(None, fast_seeded)
        _, text = _capture[0]
        # Should contain at least one formatted dollar amount
        import re
        dollar_amounts = re.findall(r"\$\d[\d,]*\.\d{2}", text)
        assert len(dollar_amounts) >= 4, (
            f"Expected at least 4 dollar amounts, found {len(dollar_amounts)}"
        )


# ═══════════════════════════════════════════════════════════════════
#  show_summary
# ═══════════════════════════════════════════════════════════════════


class TestShowSummary:
    """Account summary report captures correctly."""

    def test_contains_groups(self, fast_seeded, _capture):
        """Output includes group headers for each account type."""
        reports.show_summary(None, fast_seeded)
        assert len(_capture) == 1
        _, text = _capture[0]

        for group_label in ["ASSETS", "LIABILITIES", "EQUITY", "INCOME", "EXPENSES"]:
            assert group_label in text.upper(), (
                f"Missing group label: {group_label}"
            )

    def test_contains_net_worth(self, fast_seeded, _capture):
        """Output includes Net Worth line."""
        reports.show_summary(None, fast_seeded)
        _, text = _capture[0]
        assert "Net Worth:" in text

    def test_balanced_summary(self, fast_seeded, _capture):
        """Balanced ledger shows ✓ Balanced."""
        reports.show_summary(None, fast_seeded)
        _, text = _capture[0]
        assert "✓ Balanced" in text or "Balanced" in text


# ═══════════════════════════════════════════════════════════════════
#  show_income_stmt
# ═══════════════════════════════════════════════════════════════════


class TestShowIncomeStmt:
    """Income statement report captures correctly."""

    def test_contains_title(self, fast_seeded, _capture):
        """Output includes the title and INCOME/EXPENSES sections."""
        reports.show_income_stmt(None, fast_seeded)
        assert len(_capture) == 1
        _, text = _capture[0]
        assert "Income Statement" in text

    def test_has_sections(self, fast_seeded, _capture):
        """Has INCOME and EXPENSES sections."""
        _capture.clear()
        reports.show_income_stmt(None, fast_seeded)
        _, text = _capture[0]
        assert "INCOME" in text
        assert "EXPENSES" in text

    def test_net_income_labeled(self, fast_seeded, _capture):
        """Net income (or loss) appears in the output."""
        _capture.clear()
        reports.show_income_stmt(None, fast_seeded)
        _, text = _capture[0]
        assert "Net Income" in text or "Net Loss" in text

    def test_net_income_matches_backend(self, fast_seeded, _capture):
        """The output Net Income matches the backend's gen_income_report."""
        backend_ni = fast_seeded.gen_income_report()["net_income"]
        _capture.clear()
        reports.show_income_stmt(None, fast_seeded)
        _, text = _capture[0]

        # Parse the NI from the text: "Net Income: $X,XXX.XX" or "Net Loss: $X,XXX.XX"
        import re
        match = re.search(r"(Net Income|Net Loss):\s*([-\$0-9,\.]+)", text)
        assert match is not None, "Could not find Net Income/Loss in output"

        # Extract numeric value
        raw = match.group(2).replace("$", "").replace(",", "").strip()
        if raw.startswith("-"):
            raw = raw[1:]
            displayed_ni = -int(round(float(raw) * 100))
        else:
            displayed_ni = int(round(float(raw) * 100))

        assert displayed_ni == backend_ni, (
            f"Displayed NI {displayed_ni} != backend NI {backend_ni}"
        )


# ═══════════════════════════════════════════════════════════════════
#  show_balance_sheet
# ═══════════════════════════════════════════════════════════════════


class TestShowBalanceSheet:
    """Balance sheet report captures correctly."""

    def test_contains_sections(self, fast_seeded, _capture):
        """Output includes Assets, Liabilities, and Equity sections."""
        reports.show_balance_sheet(None, fast_seeded)
        assert len(_capture) == 1
        _, text = _capture[0]
        assert "ASSETS" in text
        assert "LIABILITIES" in text
        assert "EQUITY" in text

    def test_balanced_status(self, fast_seeded, _capture):
        """Output shows balanced status."""
        _capture.clear()
        reports.show_balance_sheet(None, fast_seeded)
        _, text = _capture[0]
        assert "Balanced" in text


# ═══════════════════════════════════════════════════════════════════
#  show_re_statement
# ═══════════════════════════════════════════════════════════════════


class TestShowReStatement:
    """Retained earnings statement capture."""

    def test_contains_sections(self, fast_seeded, _capture):
        """Output includes Beginning RE, Net Income, Ending RE."""
        reports.show_re_statement(None, fast_seeded)
        assert len(_capture) == 1
        _, text = _capture[0]
        assert "Beginning RE" in text
        assert "Net Income" in text
        assert "Ending RE" in text

    def test_beginning_re_match(self, fast_seeded, _capture):
        """Beginning RE matches the backend."""
        backend = fast_seeded.gen_retained_earnings_statement()
        _capture.clear()
        reports.show_re_statement(None, fast_seeded)
        _, text = _capture[0]

        import re
        match = re.search(r"Beginning RE:\s*([-\$0-9,\.]+)", text)
        assert match is not None
        raw = match.group(1).replace("$", "").replace(",", "").strip()
        val = int(round(float(raw) * 100))
        assert val == backend["beginning_re"], (
            f"Displayed beginning RE {val} != backend {backend['beginning_re']}"
        )


# ═══════════════════════════════════════════════════════════════════
#  show_about
# ═══════════════════════════════════════════════════════════════════


class TestShowAbout:
    """About dialog capture."""

    def test_contains_app_name(self, _capture):
        """About text includes the application name."""
        reports.show_about(None)
        assert len(_capture) == 1
        _, text = _capture[0]
        assert "Double-Entry Accounting" in text
