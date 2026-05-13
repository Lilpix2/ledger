"""
tkinter GUI package for the double-entry ledger system.

Package layout
──────────────
gui_app.py        ← Entry point — LedgerGUI main application
gui/
  __init__.py     ← Package overview + re-exports of gui/ submodules
  dialogs.py      ← Modal dialogs: AccountDialog, TransactionDialog, BuySellDialog
  reports.py      ← Report viewer functions (net worth, income statement, etc.)
  widgets.py      ← Shared widgets: AccountSelector, format_cents, build_account_choices

To launch:
    python -m ledger.gui_app
    # or: ledger  (if installed via pip)
"""

from .dialogs import AccountDialog, TransactionDialog, BuySellDialog, DeleteAccountDialog
from .reports import show_net_worth, show_summary, show_income_stmt
from .reports import show_balance_sheet, show_re_statement, show_about

__all__ = [
    "AccountDialog", "TransactionDialog", "BuySellDialog", "DeleteAccountDialog",
    "show_net_worth", "show_summary", "show_income_stmt",
    "show_balance_sheet", "show_re_statement", "show_about",
]
