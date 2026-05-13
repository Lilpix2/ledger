"""
Shared widgets and helpers used by the GUI application and dialogs.

Contains:
    format_cents()          — cents → "$1,234.56" display
    build_account_choices() — builds (choices_list, label→id map) from the account tree
    AccountSelector         — reusable Combobox wrapper with built-in label→ID mapping
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ledger.controllers.accounts import AccountManager


# ── Helpers ────────────────────────────────────────────────────────


def format_cents(cents: int | None) -> str:
    """Format an integer cent value as a USD string.

    >>> format_cents(123456)
    '$1,234.56'
    >>> format_cents(None)
    '—'
    """
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents)/100:,.2f}"


def build_account_choices(
    manager: AccountManager,
    subtype_filter: set[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """Build a list of account labels and a label→ID mapping.

    Walks the account tree recursively, producing indented labels
    suitable for display in a Combobox dropdown.

    Args:
        manager: The AccountManager holding the account tree.
        subtype_filter: If set, only include accounts with one of
                        these subtypes (e.g. ``{"brokerage", "mesp"}``).

    Returns:
        (choices_list, label_to_id_dict)

    Example label format::
        "  Checking (ASSET)"
        "    Vanguard Roth IRA (LIABILITY) [retirement]"
    """
    choices: list[str] = []
    mapping: dict[str, int] = {}
    tree_data = manager.build_tree()

    def _walk(parent_id: int, depth: int = 0):
        for cid in sorted(tree_data.get(parent_id, [])):
            acct = manager.accounts.get(cid)
            if not acct:
                continue

            # Apply subtype filter
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


# ── Reusable widgets ───────────────────────────────────────────────


class AccountSelector(ttk.Combobox):
    """A Combobox pre-populated with account choices from the account tree.

    Provides a ``selected_id`` property that returns the account ID
    corresponding to the currently displayed label (or ``None``).

    Usage::

        selector = AccountSelector(parent, manager)
        selector.pack()
        acct_id = selector.selected_id   # int | None
    """

    def __init__(
        self,
        parent: tk.Widget,
        manager: AccountManager,
        subtype_filter: set[str] | None = None,
        width: int = 42,
        **kwargs: object,
    ):
        self._manager = manager
        choices, self._label_map = build_account_choices(manager, subtype_filter)

        self._selected_id: tk.StringVar = tk.StringVar()
        super().__init__(
            parent,
            textvariable=self._selected_id,
            values=choices,
            width=width,
            state="normal",
            **kwargs,
        )

    @property
    def selected_id(self) -> int | None:
        """The account ID matching the current combobox text, or None."""
        return self._label_map.get(self._selected_id.get().strip())

    @selected_id.setter
    def selected_id(self, acct_id: int | None) -> None:
        """Set the combobox text from an account ID (closest match)."""
        if acct_id is None:
            self._selected_id.set("")
            return
        # Try to find the label matching this ID
        for label, aid in self._label_map.items():
            if aid == acct_id:
                self._selected_id.set(label)
                return
        self._selected_id.set("")
