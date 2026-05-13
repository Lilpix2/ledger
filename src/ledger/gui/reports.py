"""
Report viewer functions for the ledger GUI.

Each function opens a ``messagebox.showinfo`` with formatted text.
Reports are generated from the AccountManager backend.

Functions
---------
show_net_worth         — Assets, Liabilities, Equity, Net Income
show_summary           — Per-type account totals + equation check
show_income_stmt       — Income vs Expenses, Net Income/Loss
show_balance_sheet     — Full A = L + E statement
show_re_statement      — Beginning RE → Net Income → Dividends → Ending RE
show_about             — Application info
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING

# Imported here because reports doesn't know about format_cents until runtime
from .widgets import format_cents

if TYPE_CHECKING:
    from ledger.controllers.accounts import AccountManager


def show_net_worth(parent: tk.Widget, manager: AccountManager) -> None:
    """Display net worth (Assets − Liabilities) in an info dialog."""
    eq = manager.check_accounting_equation()
    msg = (
        f"Assets:      {format_cents(eq['assets'])}\n"
        f"Liabilities: {format_cents(eq['liabilities'])}\n"
        f"────────────────\n"
        f"Net Worth:   {format_cents(eq['net_worth'])}\n\n"
        f"Equity:      {format_cents(eq['equity'])}\n"
        f"Net Income:  {format_cents(eq['net_income'])}\n"
    )
    messagebox.showinfo("Net Worth", msg, parent=parent)


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
    messagebox.showinfo("Account Summary", "\n".join(lines), parent=parent)


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
    messagebox.showinfo("Income Statement", "\n".join(lines), parent=parent)


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
    messagebox.showinfo("Balance Sheet", "\n".join(lines), parent=parent)


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
    messagebox.showinfo("Retained Earnings Statement", msg, parent=parent)


def show_about(parent: tk.Widget) -> None:
    """Display application info dialog."""
    messagebox.showinfo(
        "About Ledger",
        "Double-Entry Accounting System\n\n"
        "A Python-based ledger with tkinter GUI.\n"
        "Supports checking, credit cards, brokerage,\n"
        "MESP, and retirement accounts.\n",
        parent=parent,
    )
