"""Component tests: PySide6 widgets — ``gui/widgets.py``.

Tests
-----
- ``format_cents`` — formatting logic and edge cases (unchanged, pure function)
- ``build_account_choices`` — tree traversal and subtype filtering (unchanged)
- ``AccountSelector`` — QComboBox wrapper: population, selection, setter, filter

Boundary
--------
Pure functions tested via ``fast_manager`` (MockDB). ``AccountSelector``
creates a QComboBox from the ``qt_app`` fixture without calling ``exec()``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from PySide6.QtWidgets import QComboBox
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    QComboBox = None  # type: ignore[assignment]


from ledger.gui_pyside.widgets import format_cents, build_account_choices, AccountSelector

from .conftest import find_widget, click_button


# ═══════════════════════════════════════════════════════════════════
#  format_cents (unchanged — pure function)
# ═══════════════════════════════════════════════════════════════════


class TestFormatCents:
    """Edge cases for ``format_cents`` — pure function, no UI needed."""

    @pytest.mark.parametrize(
        ("cents", "expected"),
        [
            (0, "$0.00"),
            (1, "$0.01"),
            (99, "$0.99"),
            (100, "$1.00"),
            (1000, "$10.00"),
            (100000, "$1,000.00"),
            (123456, "$1,234.56"),
            (99999999, "$999,999.99"),
            (-1, "-$0.01"),
            (-100, "-$1.00"),
            (-50000, "-$500.00"),
            (-123456, "-$1,234.56"),
            (None, "—"),
        ],
    )
    def test_format_cents(self, cents: int | None, expected: str) -> None:
        assert format_cents(cents) == expected


# ═══════════════════════════════════════════════════════════════════
#  build_account_choices (unchanged — pure function)
# ═══════════════════════════════════════════════════════════════════


class TestBuildAccountChoices:
    """Tree traversal and filtering — pure function, no UI needed."""

    def test_returns_two_objects(self, fast_seeded):
        """Returns (choices list, label_map dict)."""
        choices, mapping = build_account_choices(fast_seeded)
        assert isinstance(choices, list)
        assert isinstance(mapping, dict)
        assert len(choices) > 0
        assert len(mapping) == len(choices)

    def test_labels_include_type(self, fast_seeded):
        """Each choice label includes the account type in parens."""
        choices, _ = build_account_choices(fast_seeded)
        for label in choices:
            assert "(" in label, f"Label missing type: {label!r}"

    def test_hierarchy_indented(self, fast_seeded):
        """Child accounts are indented with spaces."""
        choices, _ = build_account_choices(fast_seeded)
        indented = [c for c in choices if c.startswith("  ")]
        assert len(indented) > 0, "No indented children found"

    def test_mapping_resolves(self, fast_seeded):
        """label_map returns the correct account ID."""
        choices, mapping = build_account_choices(fast_seeded)
        for label, aid in mapping.items():
            assert aid in fast_seeded.accounts, (
                f"Label {label!r} maps to unknown ID {aid}"
            )
            acct = fast_seeded.accounts[aid]
            assert acct.name in label, (
                f"Label {label!r} doesn't contain name {acct.name}"
            )

    def test_subtype_filter(self, fast_seeded):
        """Only accounts matching the subtype filter are included."""
        fast_seeded.add_account("My Checking", 1, account_subtype="checking")
        fast_seeded.add_account("My Brokerage", 1, account_subtype="brokerage")

        choices, mapping = build_account_choices(
            fast_seeded, subtype_filter={"brokerage"},
        )
        for label in choices:
            aid = mapping.get(label.strip())
            if aid:
                acct = fast_seeded.accounts.get(aid)
                if acct and acct.account_subtype:
                    assert acct.account_subtype == "brokerage"

    def test_empty_filter_excludes_all(self, fast_seeded):
        choices, _ = build_account_choices(fast_seeded, subtype_filter=set())
        assert choices == []

    def test_unknown_subtype_returns_none(self, fast_seeded):
        choices, _ = build_account_choices(
            fast_seeded, subtype_filter={"nonexistent"},
        )
        assert choices == []


# ═══════════════════════════════════════════════════════════════════
#  AccountSelector (PySide6 QComboBox wrapper)
# ═══════════════════════════════════════════════════════════════════


class TestAccountSelector:
    """Widget: ``AccountSelector`` (QComboBox wrapper for account tree).

    Black-box: interact through ``selected_id`` property and the combo
    surface (``currentIndex``, ``currentText``, ``itemText``).
    """

    def test_populated(self, qt_app, fast_seeded):
        """Selector shows all non-root accounts in its dropdown."""
        sel = AccountSelector(fast_seeded)
        assert sel.count() > 0

        for aid, acct in fast_seeded.accounts.items():
            if aid == 0:
                continue
            found = False
            for i in range(sel.count()):
                if acct.name in sel.itemText(i):
                    found = True
                    break
            assert found, f"Account {acct.name!r} not found in dropdown"

    def test_selected_id_returns_none_initially(self, qt_app, fast_seeded):
        """Before any selection, selected_id is None."""
        sel = AccountSelector(fast_seeded)
        assert sel.selected_id is None

    def test_select_item_returns_correct_id(self, qt_app, fast_seeded):
        """Selecting an item returns the correct account ID."""
        sel = AccountSelector(fast_seeded)
        # Pick the last item (usually a leaf account)
        last_idx = sel.count() - 1
        sel.setCurrentIndex(last_idx)
        text = sel.currentText().strip()

        aid = sel.selected_id
        assert aid is not None, f"selected_id is None after selecting '{text}'"
        assert isinstance(aid, int)

        acct = fast_seeded.accounts.get(aid)
        assert acct is not None
        assert acct.name in text, f"ID {aid} maps to {acct.name}, not in '{text}'"

    def test_selected_id_with_junk_text(self, qt_app, fast_seeded):
        """Setting unrecognized text via setCurrentText returns None."""
        sel = AccountSelector(fast_seeded)
        sel.setCurrentText("!! NOT AN ACCOUNT !!")
        assert sel.selected_id is None

    def test_set_selected_id_property(self, qt_app, fast_seeded):
        """Setting selected_id programmatically updates the display."""
        sel = AccountSelector(fast_seeded)

        target_id = next(
            (aid for aid, a in fast_seeded.accounts.items() if aid != 0),
            None,
        )
        assert target_id is not None, "No non-root account found"
        target_name = fast_seeded.accounts[target_id].name

        sel.selected_id = target_id
        current = sel.currentText()
        assert target_name in current, (
            f"Display text '{current}' doesn't contain '{target_name}'"
        )

    def test_set_selected_id_none_clears(self, qt_app, fast_seeded):
        """Setting selected_id to None clears the selection."""
        sel = AccountSelector(fast_seeded)
        sel.setCurrentIndex(0)
        sel.selected_id = None
        assert sel.currentIndex() < 0 or sel.currentText() == ""

    def test_selected_id_readback(self, qt_app, fast_seeded):
        """Round-trip: set ID → read back same ID via property."""
        sel = AccountSelector(fast_seeded)

        target_id = next(
            (aid for aid, a in fast_seeded.accounts.items() if aid != 0),
            None,
        )
        assert target_id is not None

        sel.selected_id = target_id
        assert sel.selected_id == target_id

    def test_subtype_filter(self, qt_app, fast_seeded):
        """AccountSelector with subtype_filter only shows matching accounts."""
        fast_seeded.add_account("My Checking", 1, account_subtype="checking")
        fast_seeded.add_account("My Brokerage", 1, account_subtype="brokerage")

        sel = AccountSelector(fast_seeded, subtype_filter={"brokerage"})
        assert sel.count() > 0

        for i in range(sel.count()):
            text = sel.itemText(i)
            assert "[brokerage]" in text or "My Brokerage" in text, (
                f"Non-brokerage label in filtered list: {text!r}"
            )

    def test_multiple_selectors_independent(self, qt_app, fast_seeded):
        """Two AccountSelectors don't share state."""
        s1 = AccountSelector(fast_seeded)
        s2 = AccountSelector(fast_seeded)

        s1.setCurrentIndex(s1.count() - 1)
        assert s1.selected_id is not None
        assert s2.selected_id is None
