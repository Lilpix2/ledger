"""
tkinter GUI for the double-entry ledger system.

This is the main entry point. The heavy lifting is split across:

    gui/dialogs.py   — AccountDialog, TransactionDialog, BuySellDialog
    gui/reports.py   — show_net_worth, show_summary, show_income_stmt, …
    gui/widgets.py   — AccountSelector, format_cents, build_account_choices

To launch::

    python -m ledger.gui_app          # development
    ledger                             # installed via pip
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections import OrderedDict

from ledger.controllers.accounts import AccountManager
from ledger.constants import DATE_STR

from .gui.dialogs import AccountDialog, TransactionDialog, BuySellDialog
from .gui.reports import (
    show_net_worth, show_summary,
    show_income_stmt, show_balance_sheet, show_re_statement,
    show_about,
)
from .gui.widgets import format_cents, build_account_choices

import os

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "journal.db")


class LedgerGUI(tk.Tk):
    """Main tkinter application window.

    Layout
    ------
    +--------------------- Menu bar ---------------------+
    | [File] [Accounts] [Transactions] [Help]             |
    +-----------------------------------------------------+
    |  Notebook: [Ledger] [Portfolio]                     |
    |  +-------------+----------------------------------+ |
    |  | Accounts    | Journal                           | |
    |  | (tree)      | (table)                          | |
    |  +-------------+----------------------------------+ |
    +-----------------------------------------------------+
    |  Status bar: Assets / Liabilities / Net Worth       |
    +-----------------------------------------------------+
    """

    def __init__(self, db_path: str = DEFAULT_DB):
        super().__init__()
        self.title("Ledger — Double-Entry Accounting")
        self.geometry("1400x800")
        self.minsize(1000, 600)

        self.manager = AccountManager(db_path)
        self.manager.generate_ledger()

        self._build_menu()
        self._build_widgets()
        self._refresh_tree()
        self._refresh_table()
        self._refresh_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ══════════════════════════════════════════════════════════════
    #  MENU
    # ══════════════════════════════════════════════════════════════

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Refresh", command=self._refresh_all, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # Accounts
        acct_menu = tk.Menu(menubar, tearoff=0)
        acct_menu.add_command(
            label="New Account…", command=self._dialog_add_account, accelerator="Ctrl+N",
        )
        acct_menu.add_separator()
        acct_menu.add_command(label="Net Worth", command=self._show_net_worth)
        acct_menu.add_command(label="Account Summary", command=self._show_summary)
        menubar.add_cascade(label="Accounts", menu=acct_menu)

        # Transactions
        txn_menu = tk.Menu(menubar, tearoff=0)
        txn_menu.add_command(
            label="New Transaction…", command=self._dialog_add_transaction,
            accelerator="Ctrl+T",
        )
        txn_menu.add_command(
            label="Buy / Sell…", command=self._dialog_buy_sell, accelerator="Ctrl+B",
        )
        txn_menu.add_separator()
        txn_menu.add_command(label="Income Statement", command=self._show_income_stmt)
        txn_menu.add_command(label="Balance Sheet", command=self._show_balance_sheet)
        txn_menu.add_command(label="RE Statement", command=self._show_re_statement)
        menubar.add_cascade(label="Transactions", menu=txn_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    # ══════════════════════════════════════════════════════════════
    #  WIDGETS
    # ══════════════════════════════════════════════════════════════

    def _build_widgets(self) -> None:
        # ── Notebook ─────────────────────────────────────────
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        self._build_ledger_tab()
        self._build_portfolio_tab()

        # ── Status bar ───────────────────────────────────────
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(
            self, textvariable=self.status_var,
            relief=tk.SUNKEN, anchor=tk.W, padding=(4, 2),
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ── Global keyboard bindings ─────────────────────────
        self.bind_all("<Control-n>", lambda e: self._dialog_add_account())
        self.bind_all("<Control-t>", lambda e: self._dialog_add_transaction())
        self.bind_all("<Control-b>", lambda e: self._dialog_buy_sell())
        self.bind_all("<Control-q>", lambda e: self._on_close())
        self.bind_all("<F5>", lambda e: self._refresh_all())

    # ── Ledger tab ────────────────────────────────────────────────

    def _build_ledger_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Ledger")

        # Toolbar
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(toolbar, text="New Account", command=self._dialog_add_account).pack(
            side=tk.LEFT, padx=2,
        )
        ttk.Button(toolbar, text="New Transaction", command=self._dialog_add_transaction).pack(
            side=tk.LEFT, padx=2,
        )
        ttk.Button(toolbar, text="Buy/Sell", command=self._dialog_buy_sell).pack(
            side=tk.LEFT, padx=2,
        )
        ttk.Button(toolbar, text="Refresh", command=self._refresh_all).pack(
            side=tk.LEFT, padx=2,
        )

        # Paned window: account tree | journal
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ── Left: Account tree ───────────────────────────────
        left_frame = ttk.LabelFrame(paned, text="Accounts")
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        acct_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        acct_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.account_tree = ttk.Treeview(
            tree_frame,
            columns=("balance", "type", "subtype"),
            displaycolumns=("balance",),
            yscrollcommand=acct_scroll_y.set,
            selectmode="browse",
        )
        acct_scroll_y.config(command=self.account_tree.yview)

        self.account_tree.heading("#0", text="Account", anchor=tk.W)
        self.account_tree.heading("balance", text="Balance", anchor=tk.E)
        self.account_tree.column("#0", width=280, minwidth=150)
        self.account_tree.column("balance", width=120, anchor=tk.E, minwidth=80)

        self.account_tree.pack(fill=tk.BOTH, expand=True)
        self.account_tree.bind("<<TreeviewSelect>>", self._on_account_select)
        self.account_tree.bind("<Button-3>", self._tree_right_click)
        paned.add(left_frame, weight=1)

        # ── Right: Journal table ────────────────────────────
        right_frame = ttk.LabelFrame(paned, text="Journal")
        table_frame = ttk.Frame(right_frame)
        table_frame.pack(fill=tk.BOTH, expand=True)

        txn_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        txn_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        txn_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        txn_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.transaction_table = ttk.Treeview(
            table_frame,
            columns=("date", "desc", "debit_acct", "credit_acct", "amount"),
            displaycolumns=("date", "desc", "amount"),
            yscrollcommand=txn_scroll_y.set,
            xscrollcommand=txn_scroll_x.set,
            selectmode="browse",
        )
        txn_scroll_y.config(command=self.transaction_table.yview)
        txn_scroll_x.config(command=self.transaction_table.xview)

        self.transaction_table.heading("#0", text="", anchor=tk.W)
        self.transaction_table.heading("date", text="Date", anchor=tk.W)
        self.transaction_table.heading("desc", text="Description", anchor=tk.W)
        self.transaction_table.heading("amount", text="Amount", anchor=tk.E)

        self.transaction_table.column("#0", width=0, minwidth=0, stretch=False)
        self.transaction_table.column("date", width=120, minwidth=90)
        self.transaction_table.column("desc", width=350, minwidth=150, stretch=True)
        self.transaction_table.column("amount", width=100, anchor=tk.E, minwidth=70)

        self.transaction_table.pack(fill=tk.BOTH, expand=True)
        self.transaction_table.bind("<Double-1>", self._on_transaction_double_click)
        paned.add(right_frame, weight=2)

    # ── Portfolio tab ─────────────────────────────────────────────

    def _build_portfolio_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Portfolio")

        # Summary label
        self.port_summary_var = tk.StringVar()
        ttk.Label(tab, textvariable=self.port_summary_var, font=("", 10, "bold")).pack(
            fill=tk.X, pady=(4, 2), padx=4,
        )

        # Table + scrollbars
        table_frame = ttk.Frame(tab)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        port_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        port_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        port_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        port_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.portfolio_table = ttk.Treeview(
            table_frame,
            columns=("account", "ticker", "shares", "cost", "price", "mkt_val", "pnl", "pnl_pct"),
            yscrollcommand=port_scroll_y.set,
            xscrollcommand=port_scroll_x.set,
            selectmode="browse",
        )
        port_scroll_y.config(command=self.portfolio_table.yview)
        port_scroll_x.config(command=self.portfolio_table.xview)

        self.portfolio_table.heading("#0", text="", anchor=tk.W)
        self.portfolio_table.heading("account", text="Account", anchor=tk.W)
        self.portfolio_table.heading("ticker", text="Ticker", anchor=tk.W)
        self.portfolio_table.heading("shares", text="Shares", anchor=tk.E)
        self.portfolio_table.heading("cost", text="Cost Basis", anchor=tk.E)
        self.portfolio_table.heading("price", text="Price", anchor=tk.E)
        self.portfolio_table.heading("mkt_val", text="Market Value", anchor=tk.E)
        self.portfolio_table.heading("pnl", text="P&L $", anchor=tk.E)
        self.portfolio_table.heading("pnl_pct", text="P&L %", anchor=tk.E)

        for col in ("account", "ticker", "shares", "cost", "price", "mkt_val", "pnl", "pnl_pct"):
            self.portfolio_table.column(col, width=100, minwidth=70, anchor=tk.E)
        self.portfolio_table.column("account", width=150, anchor=tk.W)
        self.portfolio_table.column("ticker", width=100, anchor=tk.W)
        self.portfolio_table.column("#0", width=0, stretch=False)

        self.portfolio_table.pack(fill=tk.BOTH, expand=True)

    # ══════════════════════════════════════════════════════════════
    #  REFRESH
    # ══════════════════════════════════════════════════════════════

    def _refresh_all(self) -> None:
        self.manager.generate_ledger()
        self._refresh_tree()
        self._refresh_table()
        self._refresh_portfolio()
        self._refresh_status()

    def _refresh_tree(self) -> None:
        tree = self.account_tree
        tree.delete(*tree.get_children())
        tree_data = self.manager.build_tree()

        def _add_children(parent_item: str, parent_id: int) -> None:
            for child_id in sorted(tree_data.get(parent_id, [])):
                acct = self.manager.accounts[child_id]
                bal = self.manager.get_display_balance(child_id)
                tag = f" [{acct.account_subtype}]" if acct.account_subtype else ""
                item = tree.insert(
                    parent_item, tk.END,
                    text=acct.name,
                    values=(format_cents(bal), f"{acct.acct_type}{tag}", acct.account_subtype or ""),
                    iid=str(child_id),
                    open=True,
                )
                _add_children(item, child_id)

        _add_children("", 0)

    def _refresh_table(self, filter_account_id: int | None = None) -> None:
        """Rebuild the journal table, optionally filtered by account ID."""
        table = self.transaction_table
        table.delete(*table.get_children())

        if filter_account_id:
            ids = self.manager.get_descendant_ids(filter_account_id)
        else:
            ids = set(self.manager.accounts.keys())

        for txn_id in sorted(self.manager.journal.transactions.keys()):
            txn = self.manager.journal.transactions[txn_id]

            # Filter by account if needed
            if filter_account_id:
                if not any(s.account_id in ids for s in txn.splits):
                    continue

            # Find the largest debit and credit for display
            largest_debit_amt = 0
            largest_credit_amt = 0
            for s in txn.splits:
                if s.amount > 0 and s.amount > largest_debit_amt:
                    largest_debit_amt = s.amount
                elif s.amount < 0 and abs(s.amount) > largest_credit_amt:
                    largest_credit_amt = abs(s.amount)

            total = sum(s.amount for s in txn.splits if s.amount > 0)
            table.insert(
                "", tk.END,
                values=(
                    txn.date.strftime(DATE_STR),
                    txn.description,
                    "",  # debit_acct (hidden)
                    "",  # credit_acct (hidden)
                    total,  # amount
                ),
                iid=str(txn_id),
            )

    def _refresh_portfolio(self) -> None:
        """Rebuild the portfolio tab's holdings table."""
        table = self.portfolio_table
        table.delete(*table.get_children())

        all_holdings = self.manager.get_all_holdings()
        if not all_holdings:
            self.port_summary_var.set("No investment positions")
            return

        by_account: OrderedDict[int, list] = OrderedDict()
        for h in all_holdings:
            by_account.setdefault(h.account_id, []).append(h)

        grand_cost = 0
        grand_market = 0
        grand_has_missing = False

        for acct_id, holdings_list in by_account.items():
            acct = self.manager.accounts[acct_id]

            # Account header row
            table.insert(
                "", tk.END, text="",
                values=(f"── {acct.name} ──", "", "", "", "", "", "", ""),
                tags=("header",),
            )

            acct_cost = 0
            acct_market = 0
            acct_has_price = True

            for h in holdings_list:
                price = self.manager.get_latest_price(h.ticker)
                cost = h.cost_basis_cents
                acct_cost += cost
                grand_cost += cost

                if price is not None:
                    market = int(h.shares * price)
                    pnl = market - cost
                    acct_market += market
                    pnl_pct = (pnl / cost * 100) if cost else 0
                else:
                    acct_has_price = False
                    market = None
                    pnl = None
                    pnl_pct = None

                table.insert(
                    "", tk.END, text="",
                    values=(
                        "",
                        h.ticker,
                        f"{h.shares:.4f}" if h.shares != int(h.shares) else str(int(h.shares)),
                        format_cents(cost),
                        format_cents(price),
                        format_cents(market),
                        format_cents(pnl),
                        f"{pnl_pct:+.2f}%" if pnl_pct is not None else "—",
                    ),
                )

            # Account subtotal
            if acct_has_price:
                acct_pnl = acct_market - acct_cost
                acct_pnl_pct = (acct_pnl / acct_cost * 100) if acct_cost else 0
                table.insert(
                    "", tk.END, text="",
                    values=(
                        "  Subtotal:", "", "", format_cents(acct_cost),
                        "", format_cents(acct_market),
                        format_cents(acct_pnl), f"{acct_pnl_pct:+.2f}%",
                    ),
                    tags=("subtotal",),
                )
                grand_market += acct_market
            else:
                grand_has_missing = True
                table.insert(
                    "", tk.END, text="",
                    values=("  Subtotal:", "", "", format_cents(acct_cost), "", "—", "—", "—"),
                    tags=("subtotal",),
                )

            # Blank separator
            table.insert("", tk.END, text="", values=("", "", "", "", "", "", "", ""))

        # Grand total
        if not grand_has_missing:
            grand_pnl = grand_market - grand_cost
            grand_pnl_pct = (grand_pnl / grand_cost * 100) if grand_cost else 0
            grand_total_str = format_cents(grand_cost)
            grand_market_str = format_cents(grand_market)
            grand_pnl_str = format_cents(grand_pnl)
            grand_pnl_pct_str = f"{grand_pnl_pct:+.2f}%"
            missing_warn = ""
        else:
            grand_total_str = format_cents(grand_cost)
            grand_market_str = "—"
            grand_pnl_str = "—"
            grand_pnl_pct_str = "—"
            missing_warn = "  ⚠ Some positions missing prices"

        table.insert(
            "", tk.END, text="",
            values=(
                "TOTAL", "", "", grand_total_str,
                "", grand_market_str,
                grand_pnl_str, grand_pnl_pct_str,
            ),
            tags=("total",),
        )

        self.port_summary_var.set(
            f"Total Cost: {grand_total_str}  "
            f"Market Value: {grand_market_str}  "
            f"P&L: {grand_pnl_str}  "
            f"{missing_warn}",
        )

    def _refresh_status(self) -> None:
        """Update the status bar with accounting equation summary."""
        eq = self.manager.check_accounting_equation()
        nw = eq["net_worth"]
        a = eq["assets"]
        l = eq["liabilities"]
        status = "✓" if eq["balanced"] else "✗ UNBALANCED"
        count = len(self.manager.journal.transactions)
        self.status_var.set(
            f"  Assets: {format_cents(a)}  │  Liabilities: {format_cents(l)}  │  "
            f"Net Worth: {format_cents(nw)}  │  Equation: {status}  │  "
            f"Transactions: {count}",
        )

    # ══════════════════════════════════════════════════════════════
    #  DIALOG LAUNCHERS — delegates to gui/dialogs.py
    # ══════════════════════════════════════════════════════════════

    def _dialog_add_account(self) -> None:
        AccountDialog(self, self.manager, self._refresh_all)

    def _dialog_add_transaction(self) -> None:
        TransactionDialog(self, self.manager, self._refresh_all)

    def _dialog_buy_sell(self) -> None:
        BuySellDialog(self, self.manager, self._refresh_all)

    # ══════════════════════════════════════════════════════════════
    #  REPORT LAUNCHERS — delegates to gui/reports.py
    # ══════════════════════════════════════════════════════════════

    def _show_net_worth(self) -> None:
        show_net_worth(self, self.manager)

    def _show_summary(self) -> None:
        show_summary(self, self.manager)

    def _show_income_stmt(self) -> None:
        show_income_stmt(self, self.manager)

    def _show_balance_sheet(self) -> None:
        show_balance_sheet(self, self.manager)

    def _show_re_statement(self) -> None:
        show_re_statement(self, self.manager)

    def _show_about(self) -> None:
        show_about(self)

    # ══════════════════════════════════════════════════════════════
    #  EVENTS
    # ══════════════════════════════════════════════════════════════

    def _on_account_select(self, event: object = None) -> None:
        """Filter the journal table to show only the selected account's transactions."""
        selected = self.account_tree.selection()
        if selected:
            try:
                acct_id = int(selected[0])
                self._refresh_table(filter_account_id=acct_id)
            except ValueError:
                pass

    def _on_transaction_double_click(self, event: object = None) -> None:
        """Show split details for the double-clicked journal entry."""
        selected = self.transaction_table.selection()
        if not selected:
            return
        try:
            txn_id = int(selected[0])
        except ValueError:
            return

        txn = self.manager.journal.transactions.get(txn_id)
        if not txn:
            return

        from tkinter import messagebox

        lines = [
            f"Transaction #{txn_id}",
            f"Date: {txn.date.strftime(DATE_STR)}",
            f"Description: {txn.description}",
            "",
            "Splits:",
        ]
        for s in txn.splits:
            acct = self.manager.accounts.get(s.account_id)
            acct_name = acct.name if acct else f"ID {s.account_id}"
            direction = "Dr" if s.amount > 0 else "Cr"
            lines.append(
                f"  {direction}  {acct_name:30s}  {format_cents(abs(s.amount)):>12s}",
            )
            if s.memo:
                lines.append(f"  {'':3s}  {'':30s}  {s.memo}")

        lines.append("")
        lines.append(f"Total: {format_cents(txn.total())}")

        messagebox.showinfo(f"Transaction #{txn_id}", "\n".join(lines))

    def _on_close(self) -> None:
        self.manager.db = None  # release DB connection
        self.destroy()

    def _tree_right_click(self, event: object) -> None:
        """Show account details on right-click in the account tree."""
        item = self.account_tree.identify_row(event.y)  # type: ignore[attr-defined]
        if not item:
            return
        try:
            acct_id = int(item)
        except ValueError:
            return
        acct = self.manager.accounts.get(acct_id)
        if not acct:
            return

        from tkinter import messagebox

        raw = acct.get_balance()
        display = self.manager.get_display_balance(acct_id)
        direction = "debit-normal" if self.manager.is_debit_normal(acct_id) else "credit-normal"
        subtype_info = f"Subtype: {acct.account_subtype}\n" if acct.account_subtype else ""
        holding_info = f"Holdings: {len(acct.holdings)} positions\n" if acct.holdings else ""
        parent_info = f"Parent: {self.manager.accounts[acct.parent].name}\n" if acct.parent else ""
        children = sum(1 for a in self.manager.accounts.values() if a.parent == acct_id)

        messagebox.showinfo(
            f"Account: {acct.name}",
            f"Type: {acct.acct_type}\n"
            f"{subtype_info}"
            f"Display Balance: {format_cents(display)}\n"
            f"Raw Balance: {format_cents(raw)}\n"
            f"Normal: {direction}\n"
            f"{holding_info}"
            f"{parent_info}"
            f"Children: {children}",
        )


# ── Entry point ────────────────────────────────────────────────────


def main() -> None:
    app = LedgerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
