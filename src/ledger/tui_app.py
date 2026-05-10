"""
Textual TUI for the ledger system.
"""

import calendar
from datetime import datetime, date as date_type

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Tree,
)

from .constants import DATE_STR
from .controllers.accounts import AccountManager


# ── Calendar / Date Picker ─────────────────────────────────────────


class DatePickerModal(ModalScreen[datetime | None]):
    """Modal month-view calendar to pick a date."""

    def __init__(self, year: int | None = None, month: int | None = None) -> None:
        super().__init__()
        now = datetime.now()
        self.current_year = year or now.year
        self.current_month = month or now.month
        self.today = now

    def compose(self) -> ComposeResult:
        with Vertical(id="cal-container"):
            with Horizontal(id="cal-header"):
                yield Button("◀", id="cal-prev")
                yield Static("", id="cal-month-label")
                yield Button("▶", id="cal-next")
            yield DataTable(
                id="cal-grid",
                cursor_type="cell",
                show_row_labels=False,
                zebra_stripes=False,
            )
            with Horizontal(id="cal-footer"):
                yield Button("Today", id="cal-today")
                yield Button("Cancel", variant="error", id="cal-cancel")

    def on_mount(self) -> None:
        self._render_month()

    def _render_month(self) -> None:
        """Render the current month in the grid."""
        month_name = date_type(self.current_year, self.current_month, 1).strftime("%B %Y")
        self.query_one("#cal-month-label", Static).update(f"[bold]{month_name}[/]")

        table = self.query_one("#cal-grid", DataTable)
        table.clear()
        table.add_columns("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")

        cal = calendar.monthcalendar(self.current_year, self.current_month)

        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    row.append("")
                elif (
                    self.today.year == self.current_year
                    and self.today.month == self.current_month
                    and self.today.day == day
                ):
                    row.append(f"[reverse]{day}[/]")
                else:
                    row.append(str(day))
            table.add_row(*row)

    @on(Button.Pressed, "#cal-prev")
    def _prev_month(self) -> None:
        self.current_month -= 1
        if self.current_month < 1:
            self.current_month = 12
            self.current_year -= 1
        self._render_month()

    @on(Button.Pressed, "#cal-next")
    def _next_month(self) -> None:
        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
        self._render_month()

    @on(Button.Pressed, "#cal-today")
    def _go_today(self) -> None:
        self.current_year = self.today.year
        self.current_month = self.today.month
        self._render_month()

    @on(Button.Pressed, "#cal-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(DataTable.CellSelected)
    def _day_selected(self, event: DataTable.CellSelected) -> None:
        day_str = event.value.strip()
        if not day_str:
            return
        day_str = day_str.replace("[reverse]", "").replace("[/]", "").strip()
        if not day_str.isnumeric():
            return
        day = int(day_str)
        selected = datetime(self.current_year, self.current_month, day, 0, 0, 0)
        self.dismiss(selected)


# ── Helpers (input validation) ────────────────────────────────────


def _set_valid(widget: Input, valid: bool) -> None:
    """Toggle ``valid`` / ``invalid`` CSS class on an Input."""
    widget.remove_class("valid", "invalid")
    widget.add_class("valid" if valid else "invalid")


def _valid_account_id(value: str, account_ids: set[int]) -> bool:
    return value.isnumeric() and int(value) in account_ids


# ── Modal: Add Account ─────────────────────────────────────────────


class AddAccountScreen(ModalScreen[tuple[str, int] | None]):
    """Modal for creating a new account."""

    def compose(self) -> ComposeResult:
        yield Static("── Add Account ──", id="title")
        with Vertical(id="parent-selector"):
            yield Static("Select parent account by clicking a node:", id="sel-hint")
            yield Tree("root", id="parent-tree")
        yield Static("", id="selected-parent")
        yield Input(placeholder="Account name", id="acct-name")
        yield Input(placeholder="Or type parent ID", id="acct-parent")
        with Horizontal(id="buttons"):
            yield Button("Submit", variant="primary", id="submit")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        manager = self.app.manager  # type: ignore[attr-defined]
        tree = self.query_one("#parent-tree", Tree)

        tree_data = manager.build_tree()

        def _add_children(parent_node, parent_id: int) -> None:
            for child_id in tree_data.get(parent_id, []):
                account = manager.accounts[child_id]
                label = f"{account.name}  [dim](ID {child_id})  [{account.acct_type}][/]"
                node = parent_node.add(label, data={"account_id": child_id})
                _add_children(node, child_id)

        _add_children(tree.root, 0)
        tree.root.expand()

        self.query_one("#acct-name", Input).focus()

    # ── Tree selection → Input ──────────────────────

    @on(Tree.NodeSelected, "#parent-tree")
    def _on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        account_id = event.node.data.get("account_id") if event.node.data else None
        if account_id is None:
            return

        manager = self.app.manager  # type: ignore[attr-defined]
        acct = manager.accounts[account_id]

        # Fill the parent ID input
        parent_input = self.query_one("#acct-parent", Input)
        parent_input.value = str(account_id)

        # Show confirmation
        name = acct.name.capitalize() if account_id > 0 else "Root (top-level)"
        self.query_one("#selected-parent", Static).update(
            f"[bold]Selected:[/] {name} [dim](ID {account_id})[/]"
        )

        # Mark valid
        if account_id == 0:
            _set_valid(parent_input, False)
        else:
            _set_valid(parent_input, True)

    # ── Real-time validation ────────────────────────

    @on(Input.Changed, "#acct-parent")
    def _validate_parent(self, event: Input.Changed) -> None:
        value = event.value.strip()
        input_w = event.input
        if not value:
            input_w.remove_class("valid", "invalid")
            return
        account_ids = set(self.app.manager.accounts.keys()) - {0}  # type: ignore[attr-defined]
        _set_valid(input_w, value.isnumeric() and int(value) in account_ids)

    # ── Actions ─────────────────────────────────────

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        name = self.query_one("#acct-name", Input).value.strip()
        parent_str = self.query_one("#acct-parent", Input).value.strip()
        if not name:
            self.query_one("#acct-name", Input).value = "Name is required"
            return
        if not parent_str.isnumeric():
            self.query_one("#acct-parent", Input).value = "Must be a number"
            return
        parent = int(parent_str)
        self.dismiss((name, parent))

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


# ── Modal: Add Transaction ─────────────────────────────────────────


class AddTransactionScreen(ModalScreen[tuple[datetime, str, int, int, int] | None]):
    """Modal for creating a new journal transaction."""

    def compose(self) -> ComposeResult:
        yield Static("── Add Transaction ──", id="title")
        yield Static("", id="account-list")

        with Horizontal(id="date-row"):
            yield Input(
                placeholder="MM-DD-YYYY H:M:S",
                id="txn-date",
                value=datetime.now().strftime(DATE_STR),
            )
            yield Button("📅", id="cal-btn", variant="default")

        yield Input(placeholder="Description", id="txn-desc")
        yield Input(placeholder="Debit account ID", id="txn-debit")
        yield Input(placeholder="Credit account ID", id="txn-credit")
        yield Input(placeholder="Amount (in cents)", id="txn-amount")
        with Horizontal(id="buttons"):
            yield Button("Submit", variant="primary", id="submit")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        accounts = self.app.manager.accounts  # type: ignore[attr-defined]
        lines = ["Available accounts:"]
        for acct_id, acct in sorted(accounts.items()):
            if acct_id == 0:
                continue
            lines.append(f"  {acct_id}: {acct.name}  [{acct.acct_type}]")
        self.query_one("#account-list", Static).update("\n".join(lines))
        self.query_one("#txn-date", Input).focus()

    # ── Real-time validation ────────────────────────

    @on(Input.Changed, "#txn-date")
    def _validate_date(self, event: Input.Changed) -> None:
        value = event.value.strip()
        input_w = event.input
        if not value:
            input_w.remove_class("valid", "invalid")
            return
        try:
            datetime.strptime(value, DATE_STR)
            _set_valid(input_w, True)
        except ValueError:
            _set_valid(input_w, False)

    @on(Input.Changed, "#txn-debit")
    def _validate_debit(self, event: Input.Changed) -> None:
        value = event.value.strip()
        input_w = event.input
        if not value:
            input_w.remove_class("valid", "invalid")
            return
        account_ids = set(self.app.manager.accounts.keys())  # type: ignore[attr-defined]
        _set_valid(input_w, _valid_account_id(value, account_ids))

    @on(Input.Changed, "#txn-credit")
    def _validate_credit(self, event: Input.Changed) -> None:
        value = event.value.strip()
        input_w = event.input
        if not value:
            input_w.remove_class("valid", "invalid")
            return
        account_ids = set(self.app.manager.accounts.keys())  # type: ignore[attr-defined]
        _set_valid(input_w, _valid_account_id(value, account_ids))

    @on(Input.Changed, "#txn-amount")
    def _validate_amount(self, event: Input.Changed) -> None:
        value = event.value.strip()
        input_w = event.input
        if not value:
            input_w.remove_class("valid", "invalid")
            return
        _set_valid(input_w, value.isnumeric() and int(value) > 0)

    # ── Calendar ────────────────────────────────────

    @on(Button.Pressed, "#cal-btn")
    def _open_calendar(self) -> None:
        def _handle_date(selected: datetime | None) -> None:
            if selected is not None:
                self.query_one("#txn-date", Input).value = selected.strftime(DATE_STR)
        self.app.push_screen(DatePickerModal(), _handle_date)

    # ── Submit / Cancel ─────────────────────────────

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        date_str = self.query_one("#txn-date", Input).value.strip()
        desc = self.query_one("#txn-desc", Input).value.strip()
        debit_str = self.query_one("#txn-debit", Input).value.strip()
        credit_str = self.query_one("#txn-credit", Input).value.strip()
        amount_str = self.query_one("#txn-amount", Input).value.strip()

        if not all([date_str, desc]):
            self.notify("All fields required", severity="error")
            return
        if not (debit_str.isnumeric() and credit_str.isnumeric() and amount_str.isnumeric()):
            self.notify("Account IDs and amount must be numbers", severity="error")
            return

        try:
            date = datetime.strptime(date_str, DATE_STR)
        except ValueError:
            self.query_one("#txn-date", Input).value = "Bad date format"
            return

        self.dismiss((date, desc, int(credit_str), int(debit_str), int(amount_str)))

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


# ── Main App ───────────────────────────────────────────────────────


STATUS_TEMPLATE = (
    "[b]Assets:[/] ${a:>8}  "
    "[b]Liabilities:[/] ${l:>8}  "
    "[b]Net Worth:[/] ${nw:>8}  "
    "[b]Equation:[/] {eq}"
    "  [dim](filtered: {filter})[/]"
)


class LedgerApp(App[None]):
    """Textual-based TUI for the double-entry ledger."""

    TITLE = "Ledger"
    SUB_TITLE = "Double-Entry Accounting"

    CSS = """
    /* ── Main layout ─────────────────────────────── */
    Screen {
        layout: vertical;
    }

    #main-panel {
        height: 1fr;
    }

    #tree-panel {
        width: 40%;
        border: solid $primary;
        padding: 0 1;
    }

    #tree-panel > Label {
        text-style: bold;
        padding: 0 0 1 0;
    }

    #table-panel {
        width: 60%;
        border: solid $secondary;
        padding: 0 1;
    }

    #table-panel > Label {
        text-style: bold;
        padding: 0 0 1 0;
    }

    /* ── Status bar ──────────────────────────────── */
    #status-bar {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }

    /* ── Input validation ────────────────────────── */
    Input.valid {
        border: solid $success;
    }
    Input.invalid {
        border: solid $error;
    }

    /* ── Calendar modal ──────────────────────────── */
    DatePickerModal > #cal-container {
        width: 38;
        padding: 1;
        border: thick $primary;
        background: $surface;
    }

    DatePickerModal #cal-header {
        height: 3;
        align: center middle;
    }

    DatePickerModal #cal-header > #cal-prev,
    DatePickerModal #cal-header > #cal-next {
        width: 6;
    }

    DatePickerModal #cal-month-label {
        width: 1fr;
        content-align: center middle;
        text-style: bold;
    }

    DatePickerModal #cal-footer {
        height: 3;
        align: center middle;
        margin: 1 0 0 0;
    }

    DatePickerModal #cal-footer > Button {
        margin: 0 1;
    }

    /* ── Account / Transaction modal shared ──────── */
    AddAccountScreen, AddTransactionScreen {
        align: center middle;
    }

    AddAccountScreen > #title,
    AddTransactionScreen > #title {
        text-style: bold;
        padding: 0 0 1 0;
        width: 100%;
        content-align: center middle;
    }

    AddTransactionScreen > #account-list {
        min-height: 8;
        max-height: 12;
        overflow-y: auto;
        border: solid $foreground 10%;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    AddAccountScreen #parent-selector {
        height: 14;
        margin: 0 0 1 0;
        border: solid $foreground 10%;
    }

    AddAccountScreen #parent-tree {
        height: 1fr;
    }

    AddAccountScreen #selected-parent {
        height: 1;
        text-style: italic;
        padding: 0 0 0 0;
    }

    AddTransactionScreen #date-row {
        height: 3;
        margin: 0 0 1 0;
    }

    AddTransactionScreen #date-row > #txn-date {
        width: 1fr;
    }

    AddTransactionScreen #date-row > #cal-btn {
        width: 5;
        margin: 0 0 0 1;
    }

    AddTransactionScreen Input {
        margin: 0 0 1 0;
    }

    AddAccountScreen > #buttons,
    AddTransactionScreen > #buttons {
        align: center middle;
        margin: 1 0 0 0;
    }

    AddAccountScreen Button,
    AddTransactionScreen Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("a", "add_account", "Add Account"),
        Binding("t", "add_transaction", "Add Transaction"),
        Binding("n", "net_worth", "Net Worth"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: str = "data/journal.db") -> None:
        super().__init__()
        self.manager = AccountManager(db_path)
        # When set, only show transactions related to this account (or descendants).
        self.filter_account_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-panel"):
            with Vertical(id="tree-panel"):
                yield Label("Accounts")
                yield Tree("", id="account-tree")
            with Vertical(id="table-panel"):
                yield Label("Journal")
                yield DataTable(id="transaction-table")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the tree and table on startup."""
        self.manager.generate_ledger()
        self._populate_tree()
        self._populate_table()
        self._refresh_status()

    # ── Tree ────────────────────────────────────────

    def _populate_tree(self) -> None:
        """Rebuild the account tree widget using display-normal balances."""
        tree = self.query_one("#account-tree", Tree)
        tree.clear()

        tree_data = self.manager.build_tree()

        def _add_children(parent_node, parent_id: int) -> None:
            for child_id in tree_data.get(parent_id, []):
                account = self.manager.accounts[child_id]
                balance_cents = self.manager.get_display_balance(child_id)
                label = f"{account.name}  [dim]({account.acct_type})[/]  (${balance_cents/100:,.2f})"
                node = parent_node.add(label, data={"account_id": child_id})
                _add_children(node, child_id)

        _add_children(tree.root, 0)
        tree.root.expand()

    @on(Tree.NodeSelected)
    def _on_tree_node_selected(self, event: Tree.NodeSelected[dict]) -> None:
        """Filter the journal to show only the selected account's transactions."""
        account_id = event.node.data.get("account_id") if event.node.data else None

        if account_id is not None:
            # Set the filter and show a notification with display balance
            self.filter_account_id = account_id
            account = self.manager.accounts[account_id]
            display_bal = self.manager.get_display_balance(account_id)
            raw_bal = self.manager.aggregated_balance(account_id)
            direction = "debit-normal" if self.manager.is_debit_normal(account_id) else "credit-normal"

            msg = (
                f"[bold]{account.name}[/]  [dim]({account.acct_type})[/]\n"
                f"Display balance: ${display_bal/100:,.2f}\n"
                f"Raw balance: ${raw_bal/100:,.2f}\n"
                f"Normal: {direction}\n"
                f"Type: {account.acct_type}\n"
            )
            if account.parent:
                parent_name = self.manager.accounts[account.parent].name
                msg += f"Parent: {parent_name}"
            self.notify(msg, title="Account Details", timeout=5)
        else:
            # Root node clicked — clear the filter
            self.filter_account_id = None
            self.notify("Showing all transactions")

        self._populate_table()
        self._refresh_status()

    # ── Transaction Table ───────────────────────────

    def _populate_table(self) -> None:
        """Rebuild the transaction journal table, optionally filtered."""
        table = self.query_one("#transaction-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Date", "Description", "Debit", "Credit", "Amount")
        table.zebra_stripes = True
        table.cursor_type = "row"

        # Determine filter set
        filter_ids: set[int] | None = None
        if self.filter_account_id is not None:
            filter_ids = self.manager.get_descendant_ids(self.filter_account_id)

        for txn_id in sorted(self.manager.journal.sorted_ids):
            txn = self.manager.journal.transactions[txn_id]

            # Apply filter
            if filter_ids is not None:
                if txn.debit_acct not in filter_ids and txn.credit_acct not in filter_ids:
                    continue

            table.add_row(
                txn.date.strftime(DATE_STR),
                txn.description,
                self._acct_name(txn.debit_acct),
                self._acct_name(txn.credit_acct),
                f"${txn.amount/100:,.2f}",
            )

    def _acct_name(self, acct_id: int) -> str:
        acct = self.manager.accounts.get(acct_id)
        return acct.name if acct else f"?? ({acct_id})"

    # ── Status Bar ──────────────────────────────────

    def _refresh_status(self) -> None:
        """Update the status bar with the accounting equation and net worth."""
        eq = self.manager.check_accounting_equation()
        nw = eq["net_worth"]
        a = eq["assets"]
        l = eq["liabilities"]

        filter_text = "none"
        if self.filter_account_id is not None:
            name = self.manager.accounts[self.filter_account_id].name
            filter_text = name

        balanced_str = "✓ A = L + E" if eq["balanced"] else "✗ UNBALANCED"

        self.query_one("#status-bar", Static).update(
            STATUS_TEMPLATE.format(
                a=a // 100,
                l=l // 100,
                nw=nw // 100,
                eq=balanced_str,
                filter=filter_text,
            )
        )

    # ── Actions ─────────────────────────────────────

    def action_add_account(self) -> None:
        self.push_screen(AddAccountScreen(), self._handle_add_account)

    def _handle_add_account(self, result: tuple[str, int] | None) -> None:
        if result is None:
            return
        name, parent = result
        try:
            self.manager.add_account(name, parent)
            self.manager.generate_ledger()
            self._populate_tree()
            self._refresh_status()
            self.notify(f"Account '{name}' created", severity="information")
        except ValueError as e:
            self.notify(str(e), severity="error")

    def action_add_transaction(self) -> None:
        self.push_screen(AddTransactionScreen(), self._handle_add_transaction)

    def _handle_add_transaction(self, result: tuple[datetime, str, int, int, int] | None) -> None:
        if result is None:
            return
        date, desc, credit, debit, amount = result
        try:
            self.manager.add_transaction(date, desc, credit, debit, amount)
            self.manager.generate_ledger()
            self._populate_tree()
            self._populate_table()
            self._refresh_status()
            self.notify("Transaction added", severity="information")
        except ValueError as e:
            self.notify(str(e), severity="error")

    def action_refresh(self) -> None:
        self.manager.generate_ledger()
        self._populate_tree()
        self._populate_table()
        self._refresh_status()
        self.notify("Refreshed", severity="information")

    def action_net_worth(self) -> None:
        """Show a net worth snapshot."""
        eq = self.manager.check_accounting_equation()
        nw = eq["net_worth"]
        a = eq["assets"]
        l = eq["liabilities"]
        e = eq["equity"]
        ni = eq["net_income"]

        self.notify(
            f"[bold]Net Worth Snapshot[/]\n\n"
            f"Assets:      ${a/100:>8,.2f}\n"
            f"Liabilities: ${l/100:>8,.2f}\n"
            f"───────────────\n"
            f"[bold]Net Worth:  ${nw/100:>8,.2f}[/]\n\n"
            f"Equity:      ${e/100:>8,.2f}\n"
            f"Net Income:  ${ni/100:>8,.2f}",
            title="Financial Snapshot",
            timeout=10,
        )


def main() -> None:
    app = LedgerApp()
    app.run()


if __name__ == "__main__":
    main()
