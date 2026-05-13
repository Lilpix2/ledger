"""
Report viewer functions for the ledger GUI.

Each function opens a copyable text dialog with formatted report data.
Reports are generated from the AccountManager backend.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import scrolledtext
from typing import TYPE_CHECKING

from .widgets import format_cents

if TYPE_CHECKING:
    from ledger.controllers.accounts import AccountManager


def _show_text(parent: tk.Widget, title: str, text: str) -> None:
    """Show a copyable text dialog instead of a messagebox.

    Test hook: if ``_captured_reports`` is a list, the text is
    appended as ``(title, text)`` instead of opening a dialog.
    """
    import sys

    capture = getattr(sys.modules[__name__], '_captured_reports', None)
    if capture is not None:
        capture.append((title, text))
        return

    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("600x400")
    win.transient(parent)
    win.grab_set()

    frame = ttk.Frame(win, padding=8)
    frame.pack(fill=tk.BOTH, expand=True)

    txt = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=("TkFixedFont", 10))
    txt.pack(fill=tk.BOTH, expand=True)
    txt.insert(tk.END, text)
    txt.config(state=tk.DISABLED)

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X, pady=(8, 0))

    def _copy():
        win.clipboard_clear()
        win.clipboard_append(text)

    ttk.Button(btn_frame, text="Copy to Clipboard", command=_copy).pack(
        side=tk.LEFT, padx=4
    )
    ttk.Button(btn_frame, text="Close", command=win.destroy).pack(
        side=tk.RIGHT, padx=4
    )


def show_net_worth(parent: tk.Widget, manager: AccountManager) -> None:
    """Display net worth (Assets − Liabilities) in a copyable dialog."""
    eq = manager.check_accounting_equation()
    msg = (
        f"Assets:      {format_cents(eq['assets'])}\n"
        f"Liabilities: {format_cents(eq['liabilities'])}\n"
        f"────────────────\n"
        f"Net Worth:   {format_cents(eq['net_worth'])}\n\n"
        f"Equity:      {format_cents(eq['equity'])}\n"
        f"Net Income:  {format_cents(eq['net_income'])}\n"
    )
    _show_text(parent, "Net Worth", msg)


def show_summary(parent: tk.Widget, manager: AccountManager) -> None:
    """Display per-type account summary with equation status."""
    report = manager.gen_account_summary()
    lines: list[str] = []
    for group in report["groups"]:
        if not group["accounts"]:
            continue
        lines.append(f"\n── {group['type_label']} ──")
        for _aid, name, bal in group["accounts"]:
            if bal != 0:
                lines.append(f"  {name:25s}  {format_cents(bal)}")
        total = group["total_cents"]
        lines.append(f"  {'─' * 30}")
        lines.append(f"  Total: {format_cents(total)}")
    lines.append(f"\nNet Worth: {format_cents(report['net_worth'])}")
    status = "✓ Balanced" if report["balanced"] else "✗ UNBALANCED"
    lines.append(f"Equation: {status}")
    _show_text(parent, "Account Summary", "\n".join(lines))


def show_income_stmt(parent: tk.Widget, manager: AccountManager) -> None:
    """Display income statement (revenues − expenses)."""
    report = manager.gen_income_report()
    lines = ["Income Statement\n"]
    if report["income"]:
        lines.append("INCOME:")
        for name, total in report["income"]:
            lines.append(f"  {name:25s}  {format_cents(total)}")
        lines.append(f"  Total Income: {format_cents(report['income_total'])}")
    lines.append("")
    if report["expenses"]:
        lines.append("EXPENSES:")
        for name, total in report["expenses"]:
            lines.append(f"  {name:25s}  {format_cents(total)}")
        lines.append(f"  Total Expenses: {format_cents(report['expenses_total'])}")
    lines.append("")
    ni = report["net_income"]
    label = "Net Income" if ni >= 0 else "Net Loss"
    lines.append(f"{label}: {format_cents(abs(ni))}")
    _show_text(parent, "Income Statement", "\n".join(lines))


def show_balance_sheet(parent: tk.Widget, manager: AccountManager) -> None:
    """Display balance sheet (Assets = Liabilities + Equity)."""
    bs = manager.gen_balance_sheet()
    lines = ["Balance Sheet\n"]
    lines.append("ASSETS:")
    for name, bal in bs["assets"]:
        lines.append(f"  {name:25s}  {format_cents(bal)}")
    lines.append(f"  Total Assets: {format_cents(bs['total_assets'])}")
    lines.append("")
    lines.append("LIABILITIES:")
    for name, bal in bs["liabilities"]:
        lines.append(f"  {name:25s}  {format_cents(bal)}")
    lines.append(f"  Total Liabilities: {format_cents(bs['total_liabilities'])}")
    lines.append("")
    lines.append("EQUITY:")
    for name, bal in bs["equity"]:
        lines.append(f"  {name:25s}  {format_cents(bal)}")
    lines.append(f"  Total Equity: {format_cents(bs['total_equity'])}")
    status = "✓ Balanced" if bs["balanced"] else "✗ UNBALANCED"
    lines.append(f"\nA = L + E: {status}")
    _show_text(parent, "Balance Sheet", "\n".join(lines))


def show_re_statement(parent: tk.Widget, manager: AccountManager) -> None:
    """Display retained earnings statement."""
    r = manager.gen_retained_earnings_statement()
    msg = (
        f"Beginning RE:  {format_cents(r['beginning_re'])}\n"
        f"+ Net Income:  {format_cents(r['net_income'])}\n"
    )
    if r["dividends"]:
        msg += f"- Dividends:   {format_cents(r['dividends'])}\n"
    msg += f"\nEnding RE:     {format_cents(r['ending_re'])}"
    _show_text(parent, "Retained Earnings Statement", msg)


def show_about(parent: tk.Widget) -> None:
    """Display application info dialog."""
    msg = (
        "Double-Entry Accounting System\n\n"
        "A Python-based ledger with tkinter GUI.\n"
        "Supports checking, credit cards, brokerage,\n"
        "MESP, and retirement accounts.\n"
    )
    _show_text(parent, "About Ledger", msg)
