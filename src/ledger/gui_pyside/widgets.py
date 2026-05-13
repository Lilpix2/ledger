"""
PySide6 widgets for the double-entry ledger system.

Provides:
    AccountSelector   — QComboBox subclass with built-in label→ID mapping
    format_cents      — cents → "$1,234.56" display (inline to avoid tkinter dep)
    build_account_choices — tree traversal for combo population (inline)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox


# ── Pure functions (inlined to avoid importing tkinter-based gui package) ──


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


# ── Widgets ──────────────────────────────────────────────────────────────


class AccountSelector(QComboBox):
    """A ``QComboBox`` pre-populated with account choices from the tree.

    Provides a ``selected_id`` property that returns the account ID
    corresponding to the currently selected item (or ``None``).

    Usage::

        selector = AccountSelector(manager)
        selector.selected_id          # int | None
        selector.selected_id = 5      # set by ID

    All other ``QComboBox`` methods work as normal since this
    is a ``QComboBox`` subclass.
    """

    def __init__(
        self,
        manager: Any,
        subtype_filter: set[str] | None = None,
        parent: QComboBox | None = None,
        object_name: str = "",
    ) -> None:
        super().__init__(parent)
        if object_name:
            self.setObjectName(object_name)
        self._manager = manager
        self._label_map: dict[str, int] = {}

        choices, self._label_map = build_account_choices(manager, subtype_filter)
        for label in choices:
            self.addItem(label)
        self.setEditable(True)
        # Start with no selection
        self.setCurrentIndex(-1)

    @property
    def selected_id(self) -> int | None:
        """The account ID matching the current selection, or None."""
        return self._label_map.get(self.currentText().strip())

    @selected_id.setter
    def selected_id(self, acct_id: int | None) -> None:
        """Set the selection by account ID (finds best match)."""
        if acct_id is None:
            self.setCurrentIndex(-1)
            return
        for label, aid in self._label_map.items():
            if aid == acct_id:
                self.setCurrentText(label)
                return
        self.setCurrentIndex(-1)

    def label_map(self) -> dict[str, int]:
        """Return the label→ID mapping for programmatic lookup."""
        return self._label_map
