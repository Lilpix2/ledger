"""
PySide6 widgets for the double-entry ledger system.

Stub module for TDD — AccountSelector returns NotImplementedError.
Pure functions (format_cents, build_account_choices) are duplicated
from the tkinter widgets module to avoid importing tkinter at module
load time.
"""

from __future__ import annotations

from typing import Any


# ── Pure functions (UI-agnostic, duplicated to avoid tkinter import) ──


def format_cents(cents: int | None) -> str:
    """Format an integer cent value as a USD string."""
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents)/100:,.2f}"


def build_account_choices(
    manager: Any,
    subtype_filter: set[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """Build a list of account labels and a label→ID mapping from tree data."""
    choices: list[str] = []
    mapping: dict[str, int] = {}
    tree_data = manager.build_tree()

    def _walk(parent_id: int, depth: int = 0):
        for cid in sorted(tree_data.get(parent_id, [])):
            acct = manager.accounts.get(cid)
            if not acct:
                continue
            if subtype_filter is not None:
                if acct.account_subtype not in subtype_filter:
                    _walk(cid, depth + 1)
                    continue
            prefix = "  " * depth
            label = f"{prefix}{acct.name} ({acct.acct_type})"
            if acct.account_subtype:
                label += f" [{acct.account_subtype}]"
            choices.append(label)
            mapping[label.strip()] = cid
            _walk(cid, depth + 1)

    _walk(0)
    return choices, mapping


class AccountSelector:
    """Stub: will be a QComboBox subclass.

    Expected API:
        __init__(manager, subtype_filter=None)
        selected_id -> int | None  (property, get/set)
        count() -> int
        currentText() -> str
        setCurrentIndex(index) -> None
        setCurrentText(text) -> None
        itemText(index) -> str
        currentIndex() -> int
    """

    def __init__(self, manager: Any, subtype_filter: set[str] | None = None) -> None:
        self._manager = manager
        self._items: list[str] = []
        self._label_map: dict[str, int] = {}
        self._current_idx = -1
        raise NotImplementedError("PySide6 AccountSelector not implemented yet")

    @property
    def selected_id(self) -> int | None:
        raise NotImplementedError

    @selected_id.setter
    def selected_id(self, acct_id: int | None) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def currentText(self) -> str:
        raise NotImplementedError

    def setCurrentIndex(self, index: int) -> None:
        raise NotImplementedError

    def setCurrentText(self, text: str) -> None:
        raise NotImplementedError

    def itemText(self, index: int) -> str:
        raise NotImplementedError

    def currentIndex(self) -> int:
        raise NotImplementedError
