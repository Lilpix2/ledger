"""Reports module for PySide6 GUI — stubs for TDD.

The real implementation will use QDialog + QTextEdit instead of
tkinter's scrolledtext. The capture hook mechanism is identical.
"""

from __future__ import annotations

import sys as _sys


def _show_text(parent, title: str, text: str) -> None:
    """Display report text in a copyable dialog.

    Test hook: if ``_captured_reports`` is set on this module, the text
    is captured instead of shown (for testing).
    """
    capture = getattr(_sys.modules[__name__], '_captured_reports', None)
    if capture is not None:
        capture.append((title, text))
        return
    raise NotImplementedError("PySide6 _show_text not implemented yet")


def show_net_worth(parent, manager) -> None:
    """Display net worth."""
    eq = manager.check_accounting_equation()
    from .widgets import format_cents
    msg = (
        f"Assets:      {format_cents(eq['assets'])}\n"
        f"Liabilities: {format_cents(eq['liabilities'])}\n"
        f"────────────────\n"
        f"Net Worth:   {format_cents(eq['net_worth'])}\n\n"
        f"Equity:      {format_cents(eq['equity'])}\n"
        f"Net Income:  {format_cents(eq['net_income'])}\n"
    )
    _show_text(parent, "Net Worth", msg)


def show_summary(parent, manager) -> None:
    """Display per-type account summary."""
    report = manager.gen_account_summary()
    from .widgets import format_cents
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


def show_income_stmt(parent, manager) -> None:
    """Display income statement."""
    report = manager.gen_income_report()
    from .widgets import format_cents
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


def show_balance_sheet(parent, manager) -> None:
    """Display balance sheet."""
    bs = manager.gen_balance_sheet()
    from .widgets import format_cents
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


def show_re_statement(parent, manager) -> None:
    """Display retained earnings statement."""
    r = manager.gen_retained_earnings_statement()
    from .widgets import format_cents
    msg = (
        f"Beginning RE:  {format_cents(r['beginning_re'])}\n"
        f"+ Net Income:  {format_cents(r['net_income'])}\n"
    )
    if r["dividends"]:
        msg += f"- Dividends:   {format_cents(r['dividends'])}\n"
    msg += f"\nEnding RE:     {format_cents(r['ending_re'])}"
    _show_text(parent, "Retained Earnings Statement", msg)


def show_about(parent) -> None:
    """Display application info."""
    msg = (
        "Double-Entry Accounting System\n\n"
        "A Python-based ledger with PySide6 GUI.\n"
        "Supports checking, credit cards, brokerage,\n"
        "MESP, and retirement accounts.\n"
    )
    _show_text(parent, "About Ledger", msg)
