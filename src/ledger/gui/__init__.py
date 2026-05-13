"""
tkinter GUI package for the double-entry ledger system.

Package layout
──────────────
gui_app.py        ← Entry point script (tiny wrapper)
gui/
  __init__.py     ← This file — package overview
  app.py          ← LedgerGUI main application (windows, tabs, refresh)
  dialogs.py      ← Modal dialogs: AccountDialog, TransactionDialog, BuySellDialog
  reports.py      ← Report viewer functions (net worth, income statement, etc.)
  widgets.py      ← Shared widgets: AccountSelector, format_cents, build_account_choices

To launch:
    python -m ledger.gui_app
    # or: ledger  (if installed via pip)
"""

from .app import LedgerGUI
from .reports import show_net_worth, show_summary, show_income_stmt
from .reports import show_balance_sheet, show_re_statement, show_about
from .dialogs import AccountDialog, TransactionDialog, BuySellDialog

__all__ = [
    "LedgerGUI",
    "AccountDialog", "TransactionDialog", "BuySellDialog",
    "show_net_worth", "show_summary", "show_income_stmt",
    "show_balance_sheet", "show_re_statement", "show_about",
]
