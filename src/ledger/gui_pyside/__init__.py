"""
PySide6 GUI package for the double-entry ledger system.

Stub module for TDD — tests import from here, all dialog classes
raise NotImplementedError until the real implementation is built.
Pure utility functions (format_cents, build_account_choices) are
provided inline to avoid importing the tkinter-based gui package.
"""

from .widgets import AccountSelector, format_cents, build_account_choices

__all__ = [
    "AccountSelector", "format_cents", "build_account_choices",
]
