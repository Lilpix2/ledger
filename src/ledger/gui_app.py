"""
tkinter GUI for the double-entry ledger system.

Replaces the Textual TUI with a native window interface.
Backend (AccountManager, holdings, prices) is unchanged.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
import os

# ── Ledger backend ─────────────────────────────────────────────────

from .controllers.accounts import AccountManager
from .models.data_class import Split
from .constants import DATE_STR, ACCOUNT_SUBTYPES


DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "journal.db")


# ── Helper: format cents ───────────────────────────────────────────

def _fmt(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"${cents/100:,.2f}"


# ── Main Application ───────────────────────────────────────────────


class LedgerGUI(tk.Tk):
    """tkinter-based ledger application."""

    def __init__(self, db_path: str = DEFAULT_DB):
        super().__init__()
        self.title("Ledger — Double-Entry Accounting")
        self.geometry("1200x700")
        self.minsize(800, 500)

        self.manager = AccountManager(db_path)
        self.manager.generate_ledger()

        self._build_menu()
        self._build_widgets()
        self._refresh_tree()
        self._refresh_table()
        self._refresh_status()

        # ── Protocol ─────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ══════════════════════════════════════════════════════════════
    #  MENU
    # ══════════════════════════════════════════════════════════════

    def _build_menu(self):
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
        acct_menu.add_command(label="New Account…", command=self._dialog_add_account, accelerator="Ctrl+N")
        acct_menu.add_separator()
        acct_menu.add_command(label="Net Worth", command=self._show_net_worth)
        acct_menu.add_command(label="Account Summary", command=self._show_summary)
        menubar.add_cascade(label="Accounts", menu=acct_menu)

        # Transactions
        txn_menu = tk.Menu(menubar, tearoff=0)
        txn_menu.add_command(label="New Transaction…", command=self._dialog_add_transaction, accelerator="Ctrl+T")
        txn_menu.add_command(label="Buy / Sell…", command=self._dialog_buy_sell, accelerator="Ctrl+B")
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

    def _build_widgets(self):
        # ── Main notebook ────────────────────────────────
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        # Tab 1: Ledger
        self._build_ledger_tab()

        # Tab 2: Portfolio
        self._build_portfolio_tab()

        # ── Status bar ───────────────────────────────────
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(
            self, textvariable=self.status_var,
            relief=tk.SUNKEN, anchor=tk.W, padding=(4, 2),
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ── Bindings ─────────────────────────────────────
        self.bind_all("<Control-n>", lambda e: self._dialog_add_account())
        self.bind_all("<Control-t>", lambda e: self._dialog_add_transaction())
        self.bind_all("<Control-b>", lambda e: self._dialog_buy_sell())
        self.bind_all("<Control-q>", lambda e: self._on_close())
        self.bind_all("<F5>", lambda e: self._refresh_all())

    # ── Ledger Tab ─────────────────────────────────────────────────

    def _build_ledger_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Ledger")

        # Toolbar
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(toolbar, text="New Account", command=self._dialog_add_account).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="New Transaction", command=self._dialog_add_transaction).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Buy/Sell", command=self._dialog_buy_sell).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Refresh", command=self._refresh_all).pack(side=tk.LEFT, padx=2)

        # Paned window: tree | table
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ── Left: Account tree (frame with scrollbars) ────
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
            height=20,
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

        # ── Right: Transaction table ─────────────────────
        right_frame = ttk.LabelFrame(paned, text="Journal")
        table_frame = ttk.Frame(right_frame)
        table_frame.pack(fill=tk.BOTH, expand=True)

        txn_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        txn_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.transaction_table = ttk.Treeview(
            table_frame,
            columns=("date", "desc", "debit_acct", "credit_acct", "amount"),
            displaycolumns=("date", "desc", "amount"),
            yscrollcommand=txn_scroll_y.set,
            selectmode="browse",
            height=20,
        )
        txn_scroll_y.config(command=self.transaction_table.yview)

        self.transaction_table.heading("#0", text="ID", anchor=tk.W)
        self.transaction_table.heading("date", text="Date", anchor=tk.W)
        self.transaction_table.heading("desc", text="Description", anchor=tk.W)
        self.transaction_table.heading("amount", text="Amount", anchor=tk.E)

        self.transaction_table.column("#0", width=40, minwidth=30)
        self.transaction_table.column("date", width=140, minwidth=100)
        self.transaction_table.column("desc", width=300, minwidth=150)
        self.transaction_table.column("amount", width=100, anchor=tk.E, minwidth=70)

        self.transaction_table.pack(fill=tk.BOTH, expand=True)
        self.transaction_table.bind("<Double-1>", self._on_transaction_double_click)

        paned.add(right_frame, weight=2)

    # ── Portfolio Tab ──────────────────────────────────────────────

    def _build_portfolio_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Portfolio")

        # Summary label
        self.port_summary_var = tk.StringVar()
        ttk.Label(tab, textvariable=self.port_summary_var, font=("", 10, "bold")).pack(
            fill=tk.X, pady=(4, 2), padx=4,
        )

        # Table frame with scrollbar
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
            height=20,
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

    def _refresh_all(self):
        self.manager.generate_ledger()
        self._refresh_tree()
        self._refresh_table()
        self._refresh_portfolio()
        self._refresh_status()

    def _refresh_tree(self):
        tree = self.account_tree
        tree.delete(*tree.get_children())

        tree_data = self.manager.build_tree()

        def _add_children(parent_item: str, parent_id: int):
            for child_id in sorted(tree_data.get(parent_id, [])):
                acct = self.manager.accounts[child_id]
                bal = self.manager.get_display_balance(child_id)
                tag = f" [{acct.account_subtype}]" if acct.account_subtype else ""
                item = tree.insert(
                    parent_item, tk.END,
                    text=f"{acct.name}",
                    values=(_fmt(bal), f"{acct.acct_type}{tag}", acct.account_subtype or ""),
                    iid=str(child_id),
                    open=True,
                )
                _add_children(item, child_id)

        _add_children("", 0)

    def _refresh_table(self, filter_account_id: int | None = None):
        table = self.transaction_table
        table.delete(*table.get_children())

        if filter_account_id:
            ids = self.manager.get_descendant_ids(filter_account_id)
        else:
            ids = set(self.manager.accounts.keys())

        for txn_id in sorted(self.manager.journal.transactions.keys()):
            txn = self.manager.journal.transactions[txn_id]
            # Check if any split touches the filtered accounts
            if filter_account_id:
                if not any(s.account_id in ids for s in txn.splits):
                    continue

            # Find the largest debit and credit for display
            largest_debit_amt = 0
            largest_debit_acct = ""
            largest_credit_amt = 0
            largest_credit_acct = ""

            for s in txn.splits:
                acct = self.manager.accounts.get(s.account_id)
                name = acct.name if acct else "?"
                if s.amount > 0 and s.amount > largest_debit_amt:
                    largest_debit_amt = s.amount
                    largest_debit_acct = name
                elif s.amount < 0 and abs(s.amount) > largest_credit_amt:
                    largest_credit_amt = abs(s.amount)
                    largest_credit_acct = name

            total = sum(s.amount for s in txn.splits if s.amount > 0)
            table.insert(
                "", tk.END,
                text=str(txn_id),
                values=(
                    txn.date.strftime(DATE_STR),
                    txn.description,
                    total,
                ),
                iid=str(txn_id),
            )

    def _refresh_portfolio(self):
        table = self.portfolio_table
        table.delete(*table.get_children())

        all_holdings = self.manager.get_all_holdings()
        if not all_holdings:
            self.port_summary_var.set("No investment positions")
            return

        from collections import OrderedDict
        by_account: OrderedDict[int, list] = OrderedDict()
        for h in all_holdings:
            by_account.setdefault(h.account_id, []).append(h)

        grand_cost = 0
        grand_market = 0
        grand_has_missing = False

        for acct_id, holdings_list in by_account.items():
            acct = self.manager.accounts[acct_id]

            # Account header (bold-like with tag)
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
                        _fmt(cost),
                        _fmt(price),
                        _fmt(market),
                        _fmt(pnl),
                        f"{pnl_pct:+.2f}%" if pnl_pct is not None else "—",
                    ),
                )

            if acct_has_price:
                acct_pnl = acct_market - acct_cost
                acct_pnl_pct = (acct_pnl / acct_cost * 100) if acct_cost else 0
                table.insert(
                    "", tk.END, text="",
                    values=(
                        f"  Subtotal:",
                        "", "", _fmt(acct_cost),
                        "", _fmt(acct_market),
                        _fmt(acct_pnl),
                        f"{acct_pnl_pct:+.2f}%",
                    ),
                    tags=("subtotal",),
                )
                grand_market += acct_market
            else:
                grand_has_missing = True
                table.insert(
                    "", tk.END, text="",
                    values=("  Subtotal:", "", "", _fmt(acct_cost), "", "—", "—", "—"),
                    tags=("subtotal",),
                )

            # Blank separator
            table.insert("", tk.END, text="", values=("", "", "", "", "", "", "", ""))

        # Grand total
        if not grand_has_missing:
            grand_pnl = grand_market - grand_cost
            grand_pnl_pct = (grand_pnl / grand_cost * 100) if grand_cost else 0
            grand_total_str = _fmt(grand_cost)
            grand_market_str = _fmt(grand_market)
            grand_pnl_str = _fmt(grand_pnl)
            grand_pnl_pct_str = f"{grand_pnl_pct:+.2f}%"
            missing_warn = ""
        else:
            grand_total_str = _fmt(grand_cost)
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
            f"{missing_warn}"
        )

    def _refresh_status(self):
        eq = self.manager.check_accounting_equation()
        nw = eq["net_worth"]
        a = eq["assets"]
        l = eq["liabilities"]
        status = "✓" if eq["balanced"] else "✗ UNBALANCED"
        count = len(self.manager.journal.transactions)
        self.status_var.set(
            f"  Assets: {_fmt(a)}  │  Liabilities: {_fmt(l)}  │  "
            f"Net Worth: {_fmt(nw)}  │  Equation: {status}  │  "
            f"Transactions: {count}"
        )

    # ══════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════

    def _build_account_choices(
        self, subtype_filter: set[str] | None = None
    ) -> tuple[list[str], dict[str, int]]:
        """Build a list of account labels and a label→ID mapping.

        Args:
            subtype_filter: if set, only include accounts with one of
                            these subtypes (e.g. ``{"brokerage", "mesp"}``)

        Returns:
            (choices_list, label_to_id_dict)
        """
        choices: list[str] = []
        mapping: dict[str, int] = {}
        tree_data = self.manager.build_tree()

        def _walk(parent_id: int, depth: int = 0):
            for cid in sorted(tree_data.get(parent_id, [])):
                acct = self.manager.accounts.get(cid)
                if not acct:
                    continue

                # Apply subtype filter
                if subtype_filter is not None:
                    if acct.account_subtype not in subtype_filter:
                        _walk(cid, depth + 1)
                        continue

                prefix = "  " * depth
                label = f"{prefix}{cid:3d}: {acct.name} ({acct.acct_type})"
                if acct.account_subtype:
                    label += f" [{acct.account_subtype}]"
                choices.append(label)
                mapping[label.strip()] = cid
                # Also map just the full ID part for easy lookup
                mapping[str(cid)] = cid
                _walk(cid, depth + 1)

        _walk(0)
        return choices, mapping

    def _parse_acct_id(self, raw: str) -> int | None:
        """Extract an account ID from a combobox label string or raw ID."""
        if not raw:
            return None
        if raw.strip().isdigit():
            return int(raw)
        try:
            return int(raw.split(":")[0].strip())
        except (ValueError, IndexError):
            pass
        return None

    # ══════════════════════════════════════════════════════════════
    #  EVENTS
    # ══════════════════════════════════════════════════════════════

    def _on_account_select(self, event=None):
        selected = self.account_tree.selection()
        if selected:
            try:
                acct_id = int(selected[0])
                self._refresh_table(filter_account_id=acct_id)
            except ValueError:
                pass

    def _on_transaction_double_click(self, event=None):
        """Double-click a journal entry to view its splits."""
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

        # Build the detail display
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
                f"  {direction}  {acct_name:30s}  "
                f"{_fmt(abs(s.amount)):>12s}"
            )
            if s.memo:
                lines.append(f"  {'':3s}  {'':30s}  {s.memo}")

        lines.append("")
        lines.append(f"Total: {_fmt(txn.total())}")

        messagebox.showinfo(
            f"Transaction #{txn_id}",
            "\n".join(lines),
        )

    def _on_close(self):
        self.manager.db = None  # release DB
        self.destroy()

    def _tree_right_click(self, event):
        """Right-click on tree → show account details."""
        item = self.account_tree.identify_row(event.y)
        if not item:
            return
        try:
            acct_id = int(item)
        except ValueError:
            return
        acct = self.manager.accounts.get(acct_id)
        if not acct:
            return

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
            f"Display Balance: {_fmt(display)}\n"
            f"Raw Balance: {_fmt(raw)}\n"
            f"Normal: {direction}\n"
            f"{holding_info}"
            f"{parent_info}"
            f"Children: {children}",
        )

    # ══════════════════════════════════════════════════════════════
    #  DIALOGS
    # ══════════════════════════════════════════════════════════════

    def _dialog_add_account(self):
        """Modal dialog to create a new account."""
        dialog = tk.Toplevel(self)
        dialog.title("New Account")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Parent selection
        ttk.Label(frame, text="Parent Account:").grid(row=0, column=0, sticky=tk.W, pady=2)
        parent_frame = ttk.Frame(frame)
        parent_frame.grid(row=0, column=1, sticky=tk.EW, pady=2, columnspan=2)
        frame.columnconfigure(1, weight=1)

        parent_var = tk.StringVar()
        parent_combo = ttk.Combobox(parent_frame, textvariable=parent_var, width=35)
        parent_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Populate parent choices
        parent_choices = {}
        for aid, acct in sorted(self.manager.accounts.items()):
            if aid == 0:
                continue
            parent_choices[f"{aid}: {acct.name} ({acct.acct_type})"] = aid
        parent_combo["values"] = list(parent_choices.keys())
        if parent_choices:
            parent_combo.current(0)

        # Account name
        ttk.Label(frame, text="Account Name:").grid(row=1, column=0, sticky=tk.W, pady=2)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(frame, textvariable=name_var, width=35)
        name_entry.grid(row=1, column=1, sticky=tk.EW, pady=2, columnspan=2)

        # Subtype
        ttk.Label(frame, text="Subtype (optional):").grid(row=2, column=0, sticky=tk.W, pady=2)
        subtype_var = tk.StringVar()
        subtype_combo = ttk.Combobox(frame, textvariable=subtype_var, width=35)
        subtype_combo["values"] = tuple(sorted(ACCOUNT_SUBTYPES))
        subtype_combo.grid(row=2, column=1, sticky=tk.EW, pady=2, columnspan=2)

        # Type override
        ttk.Label(frame, text="Type (optional):").grid(row=3, column=0, sticky=tk.W, pady=2)
        type_var = tk.StringVar()
        type_combo = ttk.Combobox(frame, textvariable=type_var, width=35)
        type_combo["values"] = ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")
        type_combo.grid(row=3, column=1, sticky=tk.EW, pady=2, columnspan=2)

        # Label for display
        info_label = ttk.Label(frame, text="", foreground="gray")
        info_label.grid(row=4, column=0, columnspan=3, pady=4)

        def on_parent_select(*args):
            parent_text = parent_var.get()
            pid = parent_choices.get(parent_text)
            if pid is not None and pid in self.manager.accounts:
                p_acct = self.manager.accounts[pid]
                info_label.config(text=f"Type will inherit from parent: {p_acct.acct_type}")

        parent_var.trace("w", on_parent_select)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=12)

        def submit():
            name = name_var.get().strip()
            parent_text = parent_var.get()
            if not name:
                messagebox.showerror("Error", "Account name is required", parent=dialog)
                return
            pid = parent_choices.get(parent_text)
            if pid is None:
                messagebox.showerror("Error", "Select a valid parent account", parent=dialog)
                return

            subtype = subtype_var.get().strip() or None
            acct_type = type_var.get().strip() or None

            try:
                self.manager.add_account(name, pid, acct_type, account_subtype=subtype)
                self._refresh_all()
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        ttk.Button(btn_frame, text="Create", command=submit).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

        name_entry.focus()
        dialog.wait_window()

    def _dialog_add_transaction(self):
        """Modal dialog to create a compound journal entry."""
        dialog = tk.Toplevel(self)
        dialog.title("New Transaction")
        dialog.geometry("500x450")
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Date
        ttk.Label(frame, text="Date:").grid(row=0, column=0, sticky=tk.W, pady=2)
        date_var = tk.StringVar(value=datetime.now().strftime(DATE_STR))
        date_entry = ttk.Entry(frame, textvariable=date_var, width=25)
        date_entry.grid(row=0, column=1, sticky=tk.W, pady=2)

        # Description
        ttk.Label(frame, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=2)
        desc_var = tk.StringVar()
        desc_entry = ttk.Entry(frame, textvariable=desc_var, width=40)
        desc_entry.grid(row=1, column=1, sticky=tk.EW, pady=2, columnspan=2)
        frame.columnconfigure(1, weight=1)

        # Splits section
        ttk.Label(frame, text="Splits:").grid(row=2, column=0, sticky=tk.W, pady=(8, 2))

        # Scrollable table for splits
        split_frame = ttk.Frame(frame)
        split_frame.grid(row=3, column=0, columnspan=3, sticky=tk.NSEW, pady=4)
        frame.rowconfigure(3, weight=1)

        columns = ("account", "debit", "credit", "memo")
        split_tree = ttk.Treeview(split_frame, columns=columns, show="headings", height=6)
        split_tree.heading("account", text="Account")
        split_tree.heading("debit", text="Debit (¢)")
        split_tree.heading("credit", text="Credit (¢)")
        split_tree.heading("memo", text="Memo")

        split_tree.column("account", width=120)
        split_tree.column("debit", width=80)
        split_tree.column("credit", width=80)
        split_tree.column("memo", width=120)

        split_scroll = ttk.Scrollbar(split_frame, orient=tk.VERTICAL, command=split_tree.yview)
        split_tree.configure(yscrollcommand=split_scroll.set)
        split_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        split_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Split entry form
        add_frame = ttk.LabelFrame(frame, text="Add Split", padding=6)
        add_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=6)

        # ── Account dropdown ─────────────────────────────────────
        ttk.Label(add_frame, text="Account:").grid(row=0, column=0, padx=2)
        split_acct_var = tk.StringVar()
        split_acct_choices, _ = self._build_account_choices()
        split_acct_combo = ttk.Combobox(
            add_frame, textvariable=split_acct_var,
            values=split_acct_choices,
            width=42, state="normal",
        )
        split_acct_combo.grid(row=0, column=1, padx=2, columnspan=2)

        ttk.Label(add_frame, text="Amount:").grid(row=0, column=3, padx=2)
        split_amt_var = tk.StringVar()
        split_amt_entry = ttk.Entry(add_frame, textvariable=split_amt_var, width=10)
        split_amt_entry.grid(row=0, column=4, padx=2)

        is_debit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(add_frame, text="Debit", variable=is_debit_var).grid(row=0, column=5, padx=2)

        ttk.Label(add_frame, text="Memo:").grid(row=0, column=6, padx=2)
        split_memo_var = tk.StringVar()
        memo_entry = ttk.Entry(add_frame, textvariable=split_memo_var, width=12)
        memo_entry.grid(row=0, column=7, padx=2)

        # Auto-tick D/C based on account type
        def _on_acct_select(*args):
            raw = split_acct_var.get()
            if ":" not in raw:
                return
            try:
                acct_id = int(raw.split(":")[0].strip())
            except ValueError:
                return
            acct = self.manager.accounts.get(acct_id)
            if acct:
                is_debit_var.set(self.manager.is_debit_normal(acct_id))
        split_acct_var.trace("w", _on_acct_select)

        def add_split():
            raw = split_acct_var.get()
            try:
                acct_id = int(raw.split(":")[0].strip())
            except (ValueError, IndexError):
                messagebox.showerror("Error", "Select a valid account from the dropdown", parent=dialog)
                return
            if acct_id not in self.manager.accounts:
                messagebox.showerror("Error", f"No account with ID {acct_id}", parent=dialog)
                return
            try:
                amt = int(split_amt_var.get())
            except ValueError:
                messagebox.showerror("Error", "Amount must be a number (cents)", parent=dialog)
                return
            if amt == 0:
                messagebox.showerror("Error", "Amount cannot be zero", parent=dialog)
                return

            memo = split_memo_var.get()
            if is_debit_var.get():
                split_tree.insert("", tk.END, values=(acct_id, amt, "", memo))
            else:
                split_tree.insert("", tk.END, values=(acct_id, "", amt, memo))

            split_acct_var.set("")
            split_amt_var.set("")
            split_memo_var.set("")
            split_acct_combo.focus()

        ttk.Button(add_frame, text="Add Split", command=add_split).grid(row=0, column=8, padx=4)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=12)

        def submit():
            date_str = date_var.get().strip()
            desc = desc_var.get().strip()
            if not date_str or not desc:
                messagebox.showerror("Error", "Date and description required", parent=dialog)
                return
            try:
                date = datetime.strptime(date_str, DATE_STR)
            except ValueError:
                messagebox.showerror("Error", f"Invalid date format. Use {DATE_STR}", parent=dialog)
                return

            splits = []
            for child in split_tree.get_children():
                vals = split_tree.item(child)["values"]
                acct_id = int(vals[0])
                debit = int(vals[1]) if vals[1] else 0
                credit = int(vals[2]) if vals[2] else 0
                memo = vals[3] or ""
                if debit:
                    splits.append(Split(acct_id, debit, memo))
                if credit:
                    splits.append(Split(acct_id, -credit, memo))

            if len(splits) < 2:
                messagebox.showerror("Error", "Need at least 2 splits", parent=dialog)
                return

            total = sum(s.amount for s in splits)
            if total != 0:
                messagebox.showerror(
                    "Error",
                    f"Unbalanced: debits and credits differ by {total} cents",
                    parent=dialog,
                )
                return

            try:
                self.manager.add_transaction(date, desc, splits)
                self._refresh_all()
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        ttk.Button(btn_frame, text="Submit", command=submit).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

        date_entry.focus()
        dialog.wait_window()

    def _dialog_buy_sell(self):
        """Modal dialog for buy/sell security transactions."""
        dialog = tk.Toplevel(self)
        dialog.title("Buy / Sell Security")
        dialog.geometry("520x420")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # ── Direction ─────────────────────────────────────────────────
        ttk.Label(frame, text="Direction:").grid(row=0, column=0, sticky=tk.W, pady=2)
        dir_var = tk.StringVar(value="buy")
        ttk.Radiobutton(frame, text="Buy", variable=dir_var, value="buy").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(frame, text="Sell", variable=dir_var, value="sell").grid(row=0, column=2, sticky=tk.W)

        # ── Investment account ────────────────────────────────────────
        ttk.Label(frame, text="Investment Account:").grid(row=1, column=0, sticky=tk.W, pady=2)
        inv_choices, _ = self._build_account_choices(
            subtype_filter={"brokerage", "mesp", "retirement"}
        )
        inv_var = tk.StringVar()
        inv_combo = ttk.Combobox(
            frame, textvariable=inv_var,
            values=inv_choices, width=50, state="normal",
        )
        inv_combo.grid(row=1, column=1, sticky=tk.EW, padx=4, pady=2, columnspan=2)

        # ── Cash account ─────────────────────────────────────────────
        ttk.Label(frame, text="Cash Account:").grid(row=2, column=0, sticky=tk.W, pady=2)
        cash_choices, _ = self._build_account_choices()
        cash_var = tk.StringVar()
        cash_combo = ttk.Combobox(
            frame, textvariable=cash_var,
            values=cash_choices, width=50, state="normal",
        )
        cash_combo.grid(row=2, column=1, sticky=tk.EW, padx=4, pady=2, columnspan=2)

        # ── Gains account (shown for sells) ───────────────────────────
        gains_frame = ttk.Frame(frame)
        gains_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=2)
        gains_label = ttk.Label(gains_frame, text="Gains Account (optional):")
        gains_var = tk.StringVar()

        gain_choices, _ = self._build_account_choices()
        gains_combo = ttk.Combobox(
            gains_frame, textvariable=gains_var,
            values=gain_choices, width=50, state="normal",
        )

        def toggle_gains(*args):
            if dir_var.get() == "sell":
                gains_label.pack(side=tk.LEFT)
                gains_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
            else:
                gains_label.pack_forget()
                gains_combo.pack_forget()
        dir_var.trace("w", toggle_gains)
        toggle_gains()

        # ── Ticker ───────────────────────────────────────────────────
        ttk.Label(frame, text="Ticker:").grid(row=4, column=0, sticky=tk.W, pady=2)
        ticker_var = tk.StringVar()
        ttk.Entry(frame, textvariable=ticker_var, width=15).grid(row=4, column=1, sticky=tk.W, padx=4)

        # ── Shares + Price row ───────────────────────────────────────
        sp_frame = ttk.Frame(frame)
        sp_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=2)
        ttk.Label(sp_frame, text="Shares:").pack(side=tk.LEFT)
        shares_var = tk.StringVar()
        ttk.Entry(sp_frame, textvariable=shares_var, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Label(sp_frame, text="Price (cents):").pack(side=tk.LEFT, padx=(12, 2))
        price_var = tk.StringVar()
        ttk.Entry(sp_frame, textvariable=price_var, width=12).pack(side=tk.LEFT, padx=4)

        # ── Date ─────────────────────────────────────────────────────
        ttk.Label(frame, text="Date:").grid(row=6, column=0, sticky=tk.W, pady=2)
        date_var = tk.StringVar(value=datetime.now().strftime(DATE_STR))
        ttk.Entry(frame, textvariable=date_var, width=25).grid(row=6, column=1, sticky=tk.W, padx=4, columnspan=2)

        # ── Description ──────────────────────────────────────────────
        ttk.Label(frame, text="Description:").grid(row=7, column=0, sticky=tk.W, pady=2)
        desc_var = tk.StringVar()
        ttk.Entry(frame, textvariable=desc_var, width=45).grid(
            row=7, column=1, sticky=tk.EW, padx=4, pady=2, columnspan=2,
        )

        # ── Buttons ──────────────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=12)

        def submit():
            direction = dir_var.get()
            inv_id = self._parse_acct_id(inv_var.get())
            cash_id = self._parse_acct_id(cash_var.get())

            if inv_id is None:
                messagebox.showerror("Error", "Select an investment account", parent=dialog)
                return
            if cash_id is None:
                messagebox.showerror("Error", "Select a cash account", parent=dialog)
                return

            ticker = ticker_var.get().strip().upper()
            if not ticker:
                messagebox.showerror("Error", "Ticker required", parent=dialog)
                return

            try:
                shares = float(shares_var.get())
            except ValueError:
                messagebox.showerror("Error", "Shares must be a number", parent=dialog)
                return
            if shares <= 0:
                messagebox.showerror("Error", "Shares must be positive", parent=dialog)
                return

            try:
                price_cents = int(price_var.get())
            except ValueError:
                messagebox.showerror("Error", "Price must be in cents", parent=dialog)
                return
            if price_cents <= 0:
                messagebox.showerror("Error", "Price must be positive", parent=dialog)
                return

            try:
                date = datetime.strptime(date_var.get().strip(), DATE_STR)
            except ValueError:
                messagebox.showerror("Error", f"Invalid date. Use {DATE_STR}", parent=dialog)
                return

            desc = desc_var.get().strip() or f"{direction.title()} {shares} × {ticker}"
            gain_id = self._parse_acct_id(gains_var.get())

            try:
                if direction == "buy":
                    self.manager.buy_security(date, desc, inv_id, cash_id, ticker, shares, price_cents)
                else:
                    self.manager.sell_security(date, desc, inv_id, cash_id, ticker, shares, price_cents,
                                                gain_account_id=gain_id)
                self._refresh_all()
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        ttk.Button(btn_frame, text="Submit", command=submit).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

        inv_combo.focus()
        dialog.wait_window()

    # ══════════════════════════════════════════════════════════════
    #  REPORTS
    # ══════════════════════════════════════════════════════════════

    def _show_net_worth(self):
        eq = self.manager.check_accounting_equation()
        msg = (
            f"Assets:      {_fmt(eq['assets'])}\n"
            f"Liabilities: {_fmt(eq['liabilities'])}\n"
            f"───────────────\n"
            f"Net Worth:   {_fmt(eq['net_worth'])}\n\n"
            f"Equity:      {_fmt(eq['equity'])}\n"
            f"Net Income:  {_fmt(eq['net_income'])}\n"
        )
        messagebox.showinfo("Net Worth", msg)

    def _show_summary(self):
        report = self.manager.gen_account_summary()
        lines = []
        for group in report["groups"]:
            if not group["accounts"]:
                continue
            lines.append(f"\n── {group['type_label']} ──")
            for aid, name, bal in group["accounts"]:
                if bal != 0:
                    lines.append(f"  {name:25s}  {_fmt(bal)}")
            total = group["total_cents"]
            lines.append(f"  {'─' * 30}")
            lines.append(f"  Total: {_fmt(total)}")
        lines.append(f"\nNet Worth: {_fmt(report['net_worth'])}")
        status = "✓ Balanced" if report["balanced"] else "✗ UNBALANCED"
        lines.append(f"Equation: {status}")
        messagebox.showinfo("Account Summary", "\n".join(lines))

    def _show_income_stmt(self):
        report = self.manager.gen_income_report()
        lines = ["Income Statement\n"]
        if report["income"]:
            lines.append("INCOME:")
            for name, total in report["income"]:
                lines.append(f"  {name:25s}  {_fmt(total)}")
            lines.append(f"  Total Income: {_fmt(report['income_total'])}")
        lines.append("")
        if report["expenses"]:
            lines.append("EXPENSES:")
            for name, total in report["expenses"]:
                lines.append(f"  {name:25s}  {_fmt(total)}")
            lines.append(f"  Total Expenses: {_fmt(report['expenses_total'])}")
        lines.append("")
        ni = report["net_income"]
        label = "Net Income" if ni >= 0 else "Net Loss"
        lines.append(f"{label}: {_fmt(abs(ni))}")
        messagebox.showinfo("Income Statement", "\n".join(lines))

    def _show_balance_sheet(self):
        bs = self.manager.gen_balance_sheet()
        lines = ["Balance Sheet\n"]
        lines.append("ASSETS:")
        for name, bal in bs["assets"]:
            lines.append(f"  {name:25s}  {_fmt(bal)}")
        lines.append(f"  Total Assets: {_fmt(bs['total_assets'])}")
        lines.append("")
        lines.append("LIABILITIES:")
        for name, bal in bs["liabilities"]:
            lines.append(f"  {name:25s}  {_fmt(bal)}")
        lines.append(f"  Total Liabilities: {_fmt(bs['total_liabilities'])}")
        lines.append("")
        lines.append("EQUITY:")
        for name, bal in bs["equity"]:
            lines.append(f"  {name:25s}  {_fmt(bal)}")
        lines.append(f"  Total Equity: {_fmt(bs['total_equity'])}")
        status = "✓ Balanced" if bs["balanced"] else "✗ UNBALANCED"
        lines.append(f"\nA = L + E: {status}")
        messagebox.showinfo("Balance Sheet", "\n".join(lines))

    def _show_re_statement(self):
        r = self.manager.gen_retained_earnings_statement()
        msg = (
            f"Beginning RE:  {_fmt(r['beginning_re'])}\n"
            f"+ Net Income:  {_fmt(r['net_income'])}\n"
        )
        if r["dividends"]:
            msg += f"- Dividends:   {_fmt(r['dividends'])}\n"
        msg += f"\nEnding RE:     {_fmt(r['ending_re'])}"
        messagebox.showinfo("Retained Earnings Statement", msg)

    def _show_about(self):
        messagebox.showinfo(
            "About Ledger",
            "Double-Entry Accounting System\n\n"
            "A Python-based ledger with tkinter GUI.\n"
            "Supports checking, credit cards, brokerage,\n"
            "MESP, and retirement accounts.\n"
        )


# ── Entry point ────────────────────────────────────────────────────


def main():
    app = LedgerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
