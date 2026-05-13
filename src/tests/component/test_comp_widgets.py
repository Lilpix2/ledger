"""Component tests: ``gui/widgets.py`` — shared widgets and helpers.

Tests
-----
- ``format_cents`` — formatting logic and edge cases
- ``build_account_choices`` — tree traversal and subtype filtering
- ``AccountSelector`` — instantiation, selection, setter, subtype filter

Boundary
--------
``format_cents`` and ``build_account_choices`` are pure functions tested
via ``fast_manager`` (MockDB) with no tkinter dependency.
``AccountSelector`` creates a Combobox from ``tk_root`` without ``mainloop()``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── tkinter guard ─────────────────────────────────────────────────
# AccountSelector tests need tkinter. format_cents / build_account_choices
# are pure functions but live in the same file for cohesion. Skip the
# entire module when tkinter is absent rather than forcing a split.
try:
    from tkinter import ttk
except ImportError:
    pytest.skip("tkinter not available (install python3-tk)", allow_module_level=True)
    ttk = None  # type: ignore[assignment]

from ledger.gui.widgets import format_cents, build_account_choices, AccountSelector

from .conftest import (
    first_widget,
    first_entry,
    set_entry_text,
    button_invoke,
    walk,
)


# ═══════════════════════════════════════════════════════════════════
#  format_cents
# ═══════════════════════════════════════════════════════════════════


class TestFormatCents:
    """Edge cases for ``format_cents`` — pure function, no tkinter needed."""

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
#  build_account_choices
# ═══════════════════════════════════════════════════════════════════


class TestBuildAccountChoices:
    """Tree traversal and filtering — no tkinter needed."""

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
                    assert acct.account_subtype == "brokerage", (
                        f"Filtered list includes {acct.name} ({acct.account_subtype})"
                    )

    def test_empty_filter_excludes_all(self, fast_seeded):
        """An empty subtype filter set excludes everything."""
        choices, _ = build_account_choices(fast_seeded, subtype_filter=set())
        assert choices == []

    def test_unknown_subtype_returns_none(self, fast_seeded):
        """Filtering for a nonexistent subtype returns no matches."""
        choices, _ = build_account_choices(
            fast_seeded, subtype_filter={"nonexistent"},
        )
        assert choices == []


# ═══════════════════════════════════════════════════════════════════
#  AccountSelector
# ═══════════════════════════════════════════════════════════════════


class TestAccountSelector:
    """Component widget: ``AccountSelector`` (ttk.Combobox wrapper).

    Black-box: interact through ``selected_id`` property and the combobox
    surface (``set()``, ``cget('values')``).

    Note: Root account (ID 0, name "root") is excluded from the dropdown
    so all tests use ``aid != 0`` to pick real accounts.
    """

    def test_populated(self, tk_root, fast_seeded):
        """Selector shows all non-root accounts in its dropdown."""
        sel = AccountSelector(tk_root, fast_seeded)
        choices = list(sel.cget("values"))
        assert len(choices) > 0

        for aid, acct in fast_seeded.accounts.items():
            if aid == 0:
                continue  # root account not in dropdown
            found = any(acct.name in c for c in choices)
            assert found, f"Account {acct.name!r} (ID {aid}) not found in choices"

    def test_selected_id_returns_none_initially(self, tk_root, fast_seeded):
        """Before any selection, selected_id is None."""
        sel = AccountSelector(tk_root, fast_seeded)
        assert sel.selected_id is None

    def test_set_selection_via_dropdown(self, tk_root, fast_seeded):
        """Selecting a value in the dropdown returns the correct ID."""
        sel = AccountSelector(tk_root, fast_seeded)
        choices = list(sel.cget("values"))
        target = choices[-1]
        sel.set(target)
        sel.update_idletasks()

        aid = sel.selected_id
        assert aid is not None, f"selected_id is None after setting '{target}'"
        assert isinstance(aid, int)

        acct = fast_seeded.accounts.get(aid)
        assert acct is not None
        assert acct.name in target, f"ID {aid} maps to {acct.name}, not in '{target}'"

    def test_selected_id_with_junk_text(self, tk_root, fast_seeded):
        """Entering unrecognized text returns None."""
        sel = AccountSelector(tk_root, fast_seeded)
        sel.set("!! NOT AN ACCOUNT !!")
        sel.update_idletasks()
        assert sel.selected_id is None

    def test_set_selected_id_property(self, tk_root, fast_seeded):
        """Setting selected_id programmatically updates the display text."""
        sel = AccountSelector(tk_root, fast_seeded)

        target_id = next(
            (aid for aid, a in fast_seeded.accounts.items() if aid != 0),
            None,
        )
        assert target_id is not None, "No non-root account found"
        target_name = fast_seeded.accounts[target_id].name

        sel.selected_id = target_id
        sel.update_idletasks()

        current = sel._selected_id.get()
        assert target_name in current, (
            f"Display text '{current}' doesn't contain '{target_name}'"
        )

    def test_set_selected_id_none_clears(self, tk_root, fast_seeded):
        """Setting selected_id to None clears the combobox."""
        sel = AccountSelector(tk_root, fast_seeded)
        sel.set("Some text")
        sel.update_idletasks()
        sel.selected_id = None
        sel.update_idletasks()
        assert sel._selected_id.get() == ""

    def test_subtype_filter(self, tk_root, fast_seeded):
        """AccountSelector with subtype_filter only shows matching accounts."""
        fast_seeded.add_account("My Checking", 1, account_subtype="checking")
        fast_seeded.add_account("My Brokerage", 1, account_subtype="brokerage")

        sel = AccountSelector(
            tk_root, fast_seeded, subtype_filter={"brokerage"},
        )
        choices = list(sel.cget("values"))
        assert len(choices) > 0

        for label in choices:
            assert "[brokerage]" in label or "My Brokerage" in label, (
                f"Non-brokerage label in filtered list: {label!r}"
            )

    def test_selected_id_readback(self, tk_root, fast_seeded):
        """Round-trip: set ID → read back same ID via property."""
        sel = AccountSelector(tk_root, fast_seeded)

        target_id = next(
            (aid for aid, a in fast_seeded.accounts.items() if aid != 0),
            None,
        )
        assert target_id is not None, "No non-root account found"

        sel.selected_id = target_id
        sel.update_idletasks()
        assert sel.selected_id == target_id

    def test_multiple_selectors_independent(self, tk_root, fast_seeded):
        """Two AccountSelectors on the same root don't share state."""
        s1 = AccountSelector(tk_root, fast_seeded)
        s2 = AccountSelector(tk_root, fast_seeded)

        choices = list(s1.cget("values"))
        target = choices[-1]
        s1.set(target)
        s1.update_idletasks()

        assert s1.selected_id is not None
        assert s2.selected_id is None
