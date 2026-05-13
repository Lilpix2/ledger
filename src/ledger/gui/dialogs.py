"""
Modal dialogs for the ledger GUI.

Classes
-------
AccountDialog     — Create a new account
TransactionDialog — Create a compound (multi-split) journal entry
BuySellDialog     — Buy or sell a security (brokerage / MESP / retirement)

Each dialog receives a ``manager`` for backend calls and an ``on_success``
callback that is invoked (with no arguments) after a successful operation.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import TYPE_CHECKING, Callable

import os

from ledger.models.data_class import Split
from ledger.constants import DATE_STR, ACCOUNT_SUBTYPES
from .widgets import build_account_choices

if TYPE_CHECKING:
    from ledger.controllers.accounts import AccountManager, Account


# ── New Account ────────────────────────────────────────────────────


class AccountDialog:
    """Modal dialog for creating or editing an account.

    Pass ``edit_acct`` and ``edit_acct_id`` to pre-populate for editing.

    Fields:
        • Parent account (combobox)
        • Account name
        • Subtype (optional combobox)
        • Type override (optional combobox)
    """

    def __init__(
        self,
        parent: tk.Widget,
        manager: AccountManager,
        on_success: Callable[[], None],
        edit_acct: Account | None = None,
        edit_acct_id: int | None = None,
    ):
        self.manager = manager
        self.on_success = on_success
        self.edit_acct = edit_acct
        self.edit_acct_id = edit_acct_id
        self._build(parent)

    # ── Widget layout ──────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        dialog = tk.Toplevel(parent)
        is_edit = self.edit_acct is not None
        dialog.title("Edit Account" if is_edit else "New Account")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.transient(parent)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass
        self.dialog = dialog

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # ── Parent selection ──────────────────────────────────
        ttk.Label(frame, text="Parent Account:").grid(
            row=0, column=0, sticky=tk.W, pady=2,
        )
        parent_frame = ttk.Frame(frame)
        parent_frame.grid(row=0, column=1, sticky=tk.EW, pady=2, columnspan=2)
        frame.columnconfigure(1, weight=1)

        parent_var = tk.StringVar()
        parent_combo = ttk.Combobox(parent_frame, textvariable=parent_var, width=40)
        parent_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Populate parent choices
        parent_choices: dict[str, int] = {}
        for aid, acct in sorted(self.manager.accounts.items()):
            if aid == 0:
                continue
            parent_choices[f"{acct.name} ({acct.acct_type})"] = aid
        parent_combo["values"] = list(parent_choices.keys())

        # Pre-select parent for edit mode
        if self.edit_acct:
            parent_label = f"{self.edit_acct.name} ({self.edit_acct.acct_type})"
            # Find the parent by looking up self.edit_acct.parent in the choices
            for lbl, aid in parent_choices.items():
                if aid == self.edit_acct.parent:
                    parent_combo.set(lbl)
                    break
            else:
                if parent_choices:
                    parent_combo.current(0)
        else:
            if parent_choices:
                parent_combo.current(0)

        # ── Account name ──────────────────────────────────────
        ttk.Label(frame, text="Account Name:").grid(
            row=1, column=0, sticky=tk.W, pady=2,
        )
        name_var = tk.StringVar(value=self.edit_acct.name if self.edit_acct else "")
        name_entry = ttk.Entry(frame, textvariable=name_var, width=35)
        name_entry.grid(row=1, column=1, sticky=tk.EW, pady=2, columnspan=2)

        # ── Subtype ───────────────────────────────────────────
        ttk.Label(frame, text="Subtype (optional):").grid(
            row=2, column=0, sticky=tk.W, pady=2,
        )
        subtype_var = tk.StringVar()
        subtype_combo = ttk.Combobox(frame, textvariable=subtype_var, width=35)
        subtype_combo["values"] = tuple(sorted(ACCOUNT_SUBTYPES))
        subtype_combo.grid(row=2, column=1, sticky=tk.EW, pady=2, columnspan=2)

        # ── Type override ─────────────────────────────────────
        ttk.Label(frame, text="Type (optional):").grid(
            row=3, column=0, sticky=tk.W, pady=2,
        )
        type_var = tk.StringVar()
        type_combo = ttk.Combobox(frame, textvariable=type_var, width=35)
        type_combo["values"] = ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")
        type_combo.grid(row=3, column=1, sticky=tk.EW, pady=2, columnspan=2)

        # ── Info label ────────────────────────────────────────
        info_label = ttk.Label(frame, text="", foreground="gray")
        info_label.grid(row=4, column=0, columnspan=3, pady=4)

        # Show parent type hint when selection changes
        def _on_parent_select(*args: object) -> None:
            parent_text = parent_var.get()
            pid = parent_choices.get(parent_text)
            if pid is not None and pid in self.manager.accounts:
                p_acct = self.manager.accounts[pid]
                info_label.config(
                    text=f"Type will inherit from parent: {p_acct.acct_type}",
                )

        parent_var.trace("w", _on_parent_select)

        # ── Buttons ───────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=12)

        def _submit() -> None:
            name = name_var.get().strip()
            parent_text = parent_var.get()
            if not name:
                messagebox.showerror("Error", "Account name is required", parent=dialog)
                return
            pid = parent_choices.get(parent_text)
            if pid is None:
                messagebox.showerror(
                    "Error", "Select a valid parent account", parent=dialog,
                )
                return

            subtype = subtype_var.get().strip() or None
            acct_type = type_var.get().strip() or None

            try:
                if is_edit and self.edit_acct_id is not None:
                    self.manager.update_account(
                        self.edit_acct_id, name, pid, acct_type, subtype,
                    )
                else:
                    self.manager.add_account(name, pid, acct_type, account_subtype=subtype)
                self.on_success()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=dialog)

        ttk.Button(btn_frame, text="Save" if is_edit else "Create", command=_submit).pack(
            side=tk.LEFT, padx=4,
        )
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.LEFT, padx=4,
        )

        name_entry.focus()
        dialog.wait_window()


# ── New Transaction ────────────────────────────────────────────────


class TransactionDialog:
    """Modal dialog for creating or editing a compound (multi-split) journal entry.

    Users add individual splits (account, amount, debit/credit, memo)
    one at a time, then submit the full balanced transaction.

    Pass ``edit_txn`` and ``edit_txn_id`` to pre-populate for editing:
        TransactionDialog(parent, manager, on_success,
                          edit_txn=existing_txn, edit_txn_id=5)

    Validation:
        • At least 2 splits required
        • Sum of splits must be zero (balanced double-entry)
        • Date must match ``DATE_STR`` format
        • Description and date are required
    """

    def __init__(
        self,
        parent: tk.Widget,
        manager: AccountManager,
        on_success: Callable[[], None],
        edit_txn: JournalTransaction | None = None,
        edit_txn_id: int | None = None,
    ):
        self.manager = manager
        self.on_success = on_success
        self.edit_txn = edit_txn
        self.edit_txn_id = edit_txn_id
        self._build(parent)

    # ── Widget layout ──────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        dialog = tk.Toplevel(parent)
        is_edit = self.edit_txn is not None
        dialog.title("Edit Transaction" if is_edit else "New Transaction")
        dialog.geometry("500x450")
        dialog.resizable(True, True)
        dialog.transient(parent)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass  # grab can fail if called during event processing
        self.dialog = dialog

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # ── Date ──────────────────────────────────────────────
        ttk.Label(frame, text="Date:").grid(row=0, column=0, sticky=tk.W, pady=2)
        default_date = (
            self.edit_txn.date.strftime(DATE_STR)
            if self.edit_txn else datetime.now().strftime(DATE_STR)
        )
        date_var = tk.StringVar(value=default_date)
        date_entry = ttk.Entry(frame, textvariable=date_var, width=25)
        date_entry.grid(row=0, column=1, sticky=tk.W, pady=2)

        # ── Description ───────────────────────────────────────
        ttk.Label(frame, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=2)
        default_desc = self.edit_txn.description if self.edit_txn else ""
        desc_var = tk.StringVar(value=default_desc)
        desc_entry = ttk.Entry(frame, textvariable=desc_var, width=40)
        desc_entry.grid(row=1, column=1, sticky=tk.EW, pady=2, columnspan=2)
        frame.columnconfigure(1, weight=1)

        # ── Splits section ────────────────────────────────────
        ttk.Label(frame, text="Splits:").grid(row=2, column=0, sticky=tk.W, pady=(8, 2))

        split_frame = ttk.Frame(frame)
        split_frame.grid(row=3, column=0, columnspan=3, sticky=tk.NSEW, pady=4)
        frame.rowconfigure(3, weight=1)

        columns = ("account", "debit", "credit", "memo")
        self.split_tree = ttk.Treeview(
            split_frame, columns=columns, show="headings", height=6,
        )
        self.split_tree.heading("account", text="Account")
        self.split_tree.heading("debit", text="Debit (¢)")
        self.split_tree.heading("credit", text="Credit (¢)")
        self.split_tree.heading("memo", text="Memo")

        self.split_tree.column("account", width=120)
        self.split_tree.column("debit", width=80)
        self.split_tree.column("credit", width=80)
        self.split_tree.column("memo", width=120)

        split_scroll = ttk.Scrollbar(
            split_frame, orient=tk.VERTICAL, command=self.split_tree.yview,
        )
        self.split_tree.configure(yscrollcommand=split_scroll.set)
        self.split_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        split_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Add Split form ────────────────────────────────────
        add_frame = ttk.LabelFrame(frame, text="Add Split", padding=6)
        add_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=6)

        ttk.Label(add_frame, text="Account:").grid(row=0, column=0, padx=2)
        acct_var = tk.StringVar()
        choices, acct_map = build_account_choices(self.manager)
        acct_combo = ttk.Combobox(
            add_frame, textvariable=acct_var,
            values=choices, width=42, state="normal",
        )
        acct_combo.grid(row=0, column=1, padx=2, columnspan=2)

        ttk.Label(add_frame, text="Amount:").grid(row=0, column=3, padx=2)
        amt_var = tk.StringVar()
        amt_entry = ttk.Entry(add_frame, textvariable=amt_var, width=10)
        amt_entry.grid(row=0, column=4, padx=2)

        is_debit = tk.BooleanVar(value=True)
        ttk.Checkbutton(add_frame, text="Debit", variable=is_debit).grid(
            row=0, column=5, padx=2,
        )

        ttk.Label(add_frame, text="Memo:").grid(row=0, column=6, padx=2)
        memo_var = tk.StringVar()
        memo_entry = ttk.Entry(add_frame, textvariable=memo_var, width=12)
        memo_entry.grid(row=0, column=7, padx=2)

        # Auto-tick D/C based on account type
        def _on_acct_select(*args: object) -> None:
            raw = acct_var.get().strip()
            aid = acct_map.get(raw)
            if aid is not None:
                acct = self.manager.accounts.get(aid)
                if acct:
                    is_debit.set(self.manager.is_debit_normal(aid))

        acct_var.trace("w", _on_acct_select)

        def _add_split() -> None:
            raw = acct_var.get().strip()
            aid = acct_map.get(raw)
            if aid is None:
                messagebox.showerror(
                    "Error", "Select a valid account from the dropdown", parent=dialog,
                )
                return
            if aid not in self.manager.accounts:
                messagebox.showerror(
                    "Error", f"No account with ID {aid}", parent=dialog,
                )
                return
            try:
                amt = int(amt_var.get())
            except ValueError:
                messagebox.showerror(
                    "Error", "Amount must be a number (cents)", parent=dialog,
                )
                return
            if amt == 0:
                messagebox.showerror(
                    "Error", "Amount cannot be zero", parent=dialog,
                )
                return

            memo = memo_var.get()
            acct = self.manager.accounts.get(aid)
            acct_name = acct.name if acct else f"ID {aid}"
            if is_debit.get():
                self.split_tree.insert("", tk.END, values=(acct_name, amt, "", memo))
            else:
                self.split_tree.insert("", tk.END, values=(acct_name, "", amt, memo))

            acct_var.set("")
            amt_var.set("")
            memo_var.set("")
            acct_combo.focus()

        # Delete selected split
        def _remove_split() -> None:
            selected = self.split_tree.selection()
            if selected:
                self.split_tree.delete(selected[0])

        # Edit selected split — fills the form with its values, then removes the row
        def _edit_split() -> None:
            selected = self.split_tree.selection()
            if not selected:
                return
            vals = self.split_tree.item(selected[0])["values"]
            acct_name = str(vals[0])
            debit = int(vals[1]) if vals[1] else 0
            credit = int(vals[2]) if vals[2] else 0
            memo = str(vals[3] or "")

            # Find matching label in the combo
            for label in choices:
                if label.strip() == acct_name or label.strip().startswith(acct_name):
                    acct_var.set(label)
                    break

            if debit:
                amt_var.set(str(debit))
                is_debit.set(True)
            elif credit:
                amt_var.set(str(credit))
                is_debit.set(False)
            memo_var.set(memo)

            # Remove the old row so the user can re-add the edited version
            self.split_tree.delete(selected[0])

        ttk.Button(add_frame, text="Add Split", command=_add_split).grid(
            row=0, column=8, padx=4,
        )
        ttk.Button(add_frame, text="Edit", command=_edit_split).grid(
            row=0, column=9, padx=4,
        )
        ttk.Button(add_frame, text="Remove", command=_remove_split).grid(
            row=0, column=10, padx=4,
        )
        self.split_tree.bind("<Delete>", lambda e: _remove_split())
        self.split_tree.bind("<Double-1>", lambda e: _edit_split())

        # ── Pre-populate splits when editing ─────────────────
        if self.edit_txn:
            for s in self.edit_txn.splits:
                acct = self.manager.accounts.get(s.account_id)
                acct_name = acct.name if acct else f"ID {s.account_id}"
                if s.amount > 0:
                    self.split_tree.insert(
                        "", tk.END, values=(acct_name, s.amount, "", s.memo),
                    )
                else:
                    self.split_tree.insert(
                        "", tk.END, values=(acct_name, "", -s.amount, s.memo),
                    )

        # ── Submit / Cancel ───────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=12)

        def _submit() -> None:
            date_str = date_var.get().strip()
            desc = desc_var.get().strip()
            if not date_str or not desc:
                messagebox.showerror(
                    "Error", "Date and description required", parent=dialog,
                )
                return
            try:
                date = datetime.strptime(date_str, DATE_STR)
            except ValueError:
                messagebox.showerror(
                    "Error", f"Invalid date format. Use {DATE_STR}", parent=dialog,
                )
                return

            # The split tree stores account *names* in vals[0]; look up the IDs.
            name_to_id: dict[str, int] = {
                acct.name: aid for aid, acct in self.manager.accounts.items()
            }
            splits: list[Split] = []
            for child in self.split_tree.get_children():
                vals = self.split_tree.item(child)["values"]
                acct_name = str(vals[0])
                debit = int(vals[1]) if vals[1] else 0
                credit = int(vals[2]) if vals[2] else 0
                memo = vals[3] or ""
                aid = name_to_id.get(acct_name)
                if aid is None:
                    messagebox.showerror(
                        "Error", f"Unknown account: {acct_name}", parent=dialog,
                    )
                    return
                if debit:
                    splits.append(Split(aid, debit, memo))
                if credit:
                    splits.append(Split(aid, -credit, memo))

            if len(splits) < 2:
                messagebox.showerror(
                    "Error", "Need at least 2 splits", parent=dialog,
                )
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
                # If editing, delete the old transaction first
                if is_edit and self.edit_txn_id is not None:
                    self.manager.delete_transaction(self.edit_txn_id)
                self.manager.add_transaction(date, desc, splits)
                self.on_success()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=dialog)

        ttk.Button(btn_frame, text="Submit", command=_submit).pack(
            side=tk.LEFT, padx=4,
        )
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.LEFT, padx=4,
        )

        date_entry.focus()
        dialog.wait_window()


# ── Buy / Sell Security ────────────────────────────────────────────


class BuySellDialog:
    """Modal dialog for buy/sell security transactions.

    Fields:
        • Direction (Buy / Sell)
        • Investment account (filtered to brokerage/mesp/retirement)
        • Cash account
        • Gains account (optional, shown for sells)
        • Ticker, shares, price, date, description
    """

    def __init__(
        self,
        parent: tk.Widget,
        manager: AccountManager,
        on_success: Callable[[], None],
    ):
        self.manager = manager
        self.on_success = on_success
        self._build(parent)

    # ── Widget layout ──────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        dialog = tk.Toplevel(parent)
        dialog.title("Buy / Sell Security")
        dialog.geometry("520x420")
        dialog.resizable(False, False)
        dialog.transient(parent)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass
        self.dialog = dialog

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # ── Direction ─────────────────────────────────────────
        ttk.Label(frame, text="Direction:").grid(
            row=0, column=0, sticky=tk.W, pady=2,
        )
        dir_var = tk.StringVar(value="buy")
        ttk.Radiobutton(frame, text="Buy", variable=dir_var, value="buy").grid(
            row=0, column=1, sticky=tk.W,
        )
        ttk.Radiobutton(frame, text="Sell", variable=dir_var, value="sell").grid(
            row=0, column=2, sticky=tk.W,
        )

        # ── Investment account ────────────────────────────────
        ttk.Label(frame, text="Investment Account:").grid(
            row=1, column=0, sticky=tk.W, pady=2,
        )
        inv_choices, inv_map = build_account_choices(
            self.manager, subtype_filter={"brokerage", "mesp", "retirement"},
        )
        inv_var = tk.StringVar()
        inv_combo = ttk.Combobox(
            frame, textvariable=inv_var,
            values=inv_choices, width=50, state="normal",
        )
        inv_combo.grid(row=1, column=1, sticky=tk.EW, padx=4, pady=2, columnspan=2)

        # ── Cash account ─────────────────────────────────────
        ttk.Label(frame, text="Cash Account:").grid(
            row=2, column=0, sticky=tk.W, pady=2,
        )
        cash_choices, cash_map = build_account_choices(manager)
        cash_var = tk.StringVar()
        cash_combo = ttk.Combobox(
            frame, textvariable=cash_var,
            values=cash_choices, width=50, state="normal",
        )
        cash_combo.grid(row=2, column=1, sticky=tk.EW, padx=4, pady=2, columnspan=2)

        # ── Gains account (shown for sells) ───────────────────
        gains_frame = ttk.Frame(frame)
        gains_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=2)
        gains_label = ttk.Label(gains_frame, text="Gains Account (optional):")
        gains_var = tk.StringVar()

        gain_choices, gain_map = build_account_choices(manager)
        gains_combo = ttk.Combobox(
            gains_frame, textvariable=gains_var,
            values=gain_choices, width=50, state="normal",
        )

        def _toggle_gains(*args: object) -> None:
            if dir_var.get() == "sell":
                gains_label.pack(side=tk.LEFT)
                gains_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
            else:
                gains_label.pack_forget()
                gains_combo.pack_forget()

        dir_var.trace("w", _toggle_gains)
        _toggle_gains()

        # ── Ticker ───────────────────────────────────────────
        ttk.Label(frame, text="Ticker:").grid(
            row=4, column=0, sticky=tk.W, pady=2,
        )
        ticker_var = tk.StringVar()
        ttk.Entry(frame, textvariable=ticker_var, width=15).grid(
            row=4, column=1, sticky=tk.W, padx=4,
        )

        # ── Shares + Price ───────────────────────────────────
        sp_frame = ttk.Frame(frame)
        sp_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=2)
        ttk.Label(sp_frame, text="Shares:").pack(side=tk.LEFT)
        shares_var = tk.StringVar()
        ttk.Entry(sp_frame, textvariable=shares_var, width=12).pack(
            side=tk.LEFT, padx=4,
        )
        ttk.Label(sp_frame, text="Price (cents):").pack(side=tk.LEFT, padx=(12, 2))
        price_var = tk.StringVar()
        ttk.Entry(sp_frame, textvariable=price_var, width=12).pack(
            side=tk.LEFT, padx=4,
        )

        # ── Date ─────────────────────────────────────────────
        ttk.Label(frame, text="Date:").grid(
            row=6, column=0, sticky=tk.W, pady=2,
        )
        date_var = tk.StringVar(value=datetime.now().strftime(DATE_STR))
        ttk.Entry(frame, textvariable=date_var, width=25).grid(
            row=6, column=1, sticky=tk.W, padx=4, columnspan=2,
        )

        # ── Description ──────────────────────────────────────
        ttk.Label(frame, text="Description:").grid(
            row=7, column=0, sticky=tk.W, pady=2,
        )
        desc_var = tk.StringVar()
        ttk.Entry(frame, textvariable=desc_var, width=45).grid(
            row=7, column=1, sticky=tk.EW, padx=4, pady=2, columnspan=2,
        )

        # ── Buttons ──────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=12)

        def _submit() -> None:
            direction = dir_var.get()
            inv_id = inv_map.get(inv_var.get().strip())
            cash_id = cash_map.get(cash_var.get().strip())

            if inv_id is None:
                messagebox.showerror(
                    "Error", "Select an investment account", parent=dialog,
                )
                return
            if cash_id is None:
                messagebox.showerror(
                    "Error", "Select a cash account", parent=dialog,
                )
                return

            ticker = ticker_var.get().strip().upper()
            if not ticker:
                messagebox.showerror(
                    "Error", "Ticker required", parent=dialog,
                )
                return

            try:
                shares = float(shares_var.get())
            except ValueError:
                messagebox.showerror(
                    "Error", "Shares must be a number", parent=dialog,
                )
                return
            if shares <= 0:
                messagebox.showerror(
                    "Error", "Shares must be positive", parent=dialog,
                )
                return

            try:
                price_cents = int(price_var.get())
            except ValueError:
                messagebox.showerror(
                    "Error", "Price must be in cents", parent=dialog,
                )
                return
            if price_cents <= 0:
                messagebox.showerror(
                    "Error", "Price must be positive", parent=dialog,
                )
                return

            try:
                date = datetime.strptime(date_var.get().strip(), DATE_STR)
            except ValueError:
                messagebox.showerror(
                    "Error", f"Invalid date. Use {DATE_STR}", parent=dialog,
                )
                return

            desc = desc_var.get().strip() or f"{direction.title()} {shares} × {ticker}"
            gain_id = gain_map.get(gains_var.get().strip())

            try:
                if direction == "buy":
                    self.manager.buy_security(
                        date, desc, inv_id, cash_id, ticker, shares, price_cents,
                    )
                else:
                    self.manager.sell_security(
                        date, desc, inv_id, cash_id,
                        ticker, shares, price_cents,
                        gain_account_id=gain_id,
                    )
                self.on_success()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"{type(e).__name__}: {e}", parent=dialog)

        ttk.Button(btn_frame, text="Submit", command=_submit).pack(
            side=tk.LEFT, padx=4,
        )
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.LEFT, padx=4,
        )

        inv_combo.focus()
        dialog.wait_window()


# ── CSV Import / Account Mapping ──────────────────────────────────


class CSVImportDialog:
    """Dialog to map CSV categories to ledger accounts before importing.

    Scans the CSV for unique categories, auto-detects account types,
    and lets the user customize each mapping before import proceeds.
    """

    def __init__(
        self,
        parent: tk.Widget,
        csv_path: str,
        suggested_account: str,
        manager: AccountManager,
    ):
        import csv
        self.manager = manager
        self.csv_path = csv_path
        self.result: dict | None = None

        # Parse CSV and detect categories
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.rows = list(reader)

        cats: dict[str, list[dict]] = {}
        for row in self.rows:
            cat = (row.get("Category") or "").strip()
            if cat:
                if cat not in cats:
                    cats[cat] = []
                if len(cats[cat]) < 2:
                    cats[cat].append({
                        "date": row.get("Date", ""),
                        "amount": row.get("Amount", ""),
                        "payee": row.get("Payee", "")[:30],
                    })

        self.categories: list[dict] = []
        for cat in sorted(cats.keys()):
            samples = cats[cat]
            amts = [float(s["amount"]) for s in samples if s["amount"]]
            net_amt = sum(amts) if amts else 0
            acct_type = self._suggest_type(cat)
            self.categories.append({
                "raw": cat,
                "samples": samples,
                "net": net_amt,
                "type": acct_type,
                "account_name": self._suggest_name(cat, acct_type),
            })

        self._build(parent)

    @staticmethod
    def _suggest_type(cat: str) -> str:
        if cat.startswith("["):
            return "ASSET"
        lower = cat.lower()
        if "income" in lower:
            return "INCOME"
        if "expense" in lower:
            return "EXPENSE"
        return "EXPENSE"

    @staticmethod
    def _suggest_name(cat: str, acct_type: str) -> str:
        """Suggest a ledger account name from the category."""
        name = cat.strip("[]").strip()
        # Clean up common prefixes
        if "/Alex" in name:
            name = name.replace("/Alex", "")
        if ":" in name:
            parts = name.split(":")
            name = parts[-1]
        return name.strip()

    def _build(self, parent: tk.Widget) -> None:
        dialog = tk.Toplevel(parent)
        dialog.title("CSV Import — Category Mapping")
        dialog.geometry("600x500")
        dialog.resizable(True, True)
        dialog.transient(parent)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass
        self.dialog = dialog

        top_frame = ttk.Frame(dialog, padding=8)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text=f"File: {os.path.basename(self.csv_path)}").pack(anchor=tk.W)
        ttk.Label(top_frame, text=f"Rows: {len(self.rows)}  |  "
                  f"Categories: {len(self.categories)}").pack(anchor=tk.W)

        # Account name for this file
        acct_frame = ttk.Frame(dialog, padding=8)
        acct_frame.pack(fill=tk.X)
        ttk.Label(acct_frame, text="Import into account:").pack(side=tk.LEFT)
        self.acct_var = tk.StringVar(value=self._suggested_acct_name())
        ttk.Entry(acct_frame, textvariable=self.acct_var, width=40).pack(
            side=tk.LEFT, padx=4,
        )

        # Categories table
        list_frame = ttk.LabelFrame(dialog, text="Category Mapping", padding=4)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Scrollable area
        canvas = tk.Canvas(list_frame, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Header row
        header = ttk.Frame(scrollable)
        header.pack(fill=tk.X, pady=2)
        for i, (text, w) in enumerate([
            ("Category", 140), ("Type", 80), ("Account Name", 200), ("Sample", 120),
        ]):
            ttk.Label(header, text=text, font=("", 9, "bold"), width=w//7).pack(
                side=tk.LEFT, padx=2,
            )

        ttk.Separator(scrollable, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        self.category_widgets: list[dict] = []

        for cat_info in self.categories:
            frame = ttk.Frame(scrollable)
            frame.pack(fill=tk.X, pady=1)

            # Raw category
            ttk.Label(frame, text=cat_info["raw"][:25], width=20).pack(
                side=tk.LEFT, padx=2,
            )
            # Editable type
            type_var = tk.StringVar(value=cat_info["type"])
            type_combo = ttk.Combobox(frame, textvariable=type_var,
                                       values=("ASSET", "LIABILITY", "INCOME", "EXPENSE"),
                                       width=9, state="readonly")
            type_combo.pack(side=tk.LEFT, padx=2)
            # Editable account name
            name_var = tk.StringVar(value=cat_info["account_name"])
            entry = ttk.Entry(frame, textvariable=name_var, width=28)
            entry.pack(side=tk.LEFT, padx=2)
            # Sample
            sample_text = cat_info["samples"][0]["payee"] if cat_info["samples"] else ""
            ttk.Label(frame, text=sample_text[:20], width=18).pack(
                side=tk.LEFT, padx=2,
            )

            self.category_widgets.append({
                "raw": cat_info["raw"],
                "name_var": name_var,
                "type_var": type_var,
            })

        # Buttons
        btn_frame = ttk.Frame(dialog, padding=8)
        btn_frame.pack(fill=tk.X)

        def _cancel() -> None:
            self.result = None
            dialog.destroy()

        def _proceed() -> None:
            acct_name = self.acct_var.get().strip()
            if not acct_name:
                from tkinter import messagebox
                messagebox.showerror("Error", "Account name is required", parent=dialog)
                return

            # Build the mapping
            cat_map: dict[str, int] = {}
            for w in self.category_widgets:
                raw = w["raw"]
                name = w["name_var"].get().strip() or f"Imported {raw[:20]}"
                acct_type = w["type_var"].get()

                # Find or create account
                parent_map = {"ASSET": 1, "LIABILITY": 2, "INCOME": 4, "EXPENSE": 5}
                pid = parent_map.get(acct_type, 5)

                aid = None
                for existing_aid, a in self.manager.accounts.items():
                    if a.name == name and a.parent == pid:
                        aid = existing_aid
                        break
                    if a.name == name and a.acct_type == acct_type:
                        aid = existing_aid
                        break

                if aid is None:
                    aid = self.manager.add_account(name, pid, acct_type)

                cat_map[raw] = aid

            self.result = {
                "account_name": acct_name,
                "cat_map": cat_map,
                "total_rows": len(self.rows),
            }
            dialog.destroy()

        ttk.Button(btn_frame, text="Cancel", command=_cancel).pack(
            side=tk.RIGHT, padx=4,
        )
        ttk.Button(btn_frame, text="Import", command=_proceed).pack(
            side=tk.RIGHT, padx=4,
        )

        dialog.wait_window()

    def _suggested_acct_name(self) -> str:
        basename = os.path.splitext(os.path.basename(self.csv_path))[0]
        # Clean up UUID suffixes
        if "---" in basename:
            basename = basename.split("---")[0]
        return basename.replace("_", " ").title().strip()
