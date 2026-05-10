"""
Textual TUI for the ledger system.
"""

from datetime import datetime

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


# ── Modal Screens ──────────────────────────────────────────────────


class AddAccountScreen(ModalScreen[tuple[str, int] | None]):
    """Modal for creating a new account."""

    def compose(self) -> ComposeResult:
        yield Static("── Add Account ──", id="title")
        yield Static("", id="account-list")
        yield Input(placeholder="Account name", id="acct-name")
        yield Input(placeholder="Parent account ID", id="acct-parent")
        with Horizontal(id="buttons"):
            yield Button("Submit", variant="primary", id="submit")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Show available parent accounts when the modal opens."""
        accounts = self.app.manager.accounts  # type: ignore[attr-defined]
        lines = ["Available accounts:"]
        for acct_id, acct in sorted(accounts.items()):
            if acct_id == 0:
                continue
            lines.append(f"  {acct_id}: {acct.name}")
        self.query_one("#account-list", Static).update("\n".join(lines))

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


class AddTransactionScreen(ModalScreen[tuple[datetime, str, int, int, int] | None]):
    """Modal for creating a new journal transaction."""

    def compose(self) -> ComposeResult:
        yield Static("── Add Transaction ──", id="title")
        yield Static("", id="account-list")
        yield Input(placeholder="Date (MM-DD-YYYY H:M:S)", id="txn-date")
        yield Input(placeholder="Description", id="txn-desc")
        yield Input(placeholder="Debit account ID", id="txn-debit")
        yield Input(placeholder="Credit account ID", id="txn-credit")
        yield Input(placeholder="Amount (in cents)", id="txn-amount")
        with Horizontal(id="buttons"):
            yield Button("Submit", variant="primary", id="submit")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Show available accounts."""
        accounts = self.app.manager.accounts  # type: ignore[attr-defined]
        lines = ["Available accounts:"]
        for acct_id, acct in sorted(accounts.items()):
            if acct_id == 0:
                continue
            lines.append(f"  {acct_id}: {acct.name}")
        self.query_one("#account-list", Static).update("\n".join(lines))

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

    /* ── Modal screen shared ─────────────────────── */
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

    AddAccountScreen > #account-list,
    AddTransactionScreen > #account-list {
        min-height: 8;
        max-height: 12;
        overflow-y: auto;
        border: solid $foreground 10%;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    AddAccountScreen Input,
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
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: str = "data/journal.db") -> None:
        super().__init__()
        self.manager = AccountManager(db_path)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-panel"):
            with Vertical(id="tree-panel"):
                yield Label("Accounts")
                yield Tree("", id="account-tree")
            with Vertical(id="table-panel"):
                yield Label("Journal")
                yield DataTable(id="transaction-table")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the tree and table on startup."""
        self.manager.generate_ledger()
        self._populate_tree()
        self._populate_table()

    # ── Tree ────────────────────────────────────────

    def _populate_tree(self) -> None:
        """Rebuild the account tree widget from the current state."""
        tree = self.query_one("#account-tree", Tree)
        tree.clear()

        tree_data = self.manager.build_tree()

        def _add_children(parent_node, parent_id: int) -> None:
            for child_id in tree_data.get(parent_id, []):
                account = self.manager.accounts[child_id]
                balance_cents = account.get_balance()
                label = f"{account.name}  (${balance_cents/100:,.2f})"
                node = parent_node.add(label, data={"account_id": child_id})
                _add_children(node, child_id)

        _add_children(tree.root, 0)
        tree.root.expand()

    @on(Tree.NodeSelected)
    def _on_tree_node_selected(self, event: Tree.NodeSelected[dict]) -> None:
        """Show account details when a tree node is selected."""
        account_id = event.node.data.get("account_id") if event.node.data else None
        if account_id is not None:
            account = self.manager.accounts[account_id]
            self.notify(
                f"[bold]{account.name}[/]\n"
                f"Balance: ${account.get_balance()/100:,.2f}\n"
                f"Parent: {self.manager.accounts[account.parent].name if account.parent else 'None'}",
                title="Account Details",
                timeout=5,
            )

    # ── Transaction Table ───────────────────────────

    def _populate_table(self) -> None:
        """Rebuild the transaction journal table."""
        table = self.query_one("#transaction-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Date", "Description", "Debit", "Credit", "Amount")

        for txn_id in sorted(self.manager.journal.sorted_ids):
            txn = self.manager.journal.transactions[txn_id]
            table.add_row(
                txn.date.strftime(DATE_STR),
                txn.description,
                self._acct_name(txn.debit_acct),
                self._acct_name(txn.credit_acct),
                f"${txn.amount/100:,.2f}",
            )

    def _acct_name(self, acct_id: int) -> str:
        """Return the display name of an account."""
        acct = self.manager.accounts.get(acct_id)
        return acct.name if acct else f"?? ({acct_id})"

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
            self.notify(f"Account '{name}' created", severity="information")
        except ValueError as e:
            self.notify(str(e), severity="error")

    def action_add_transaction(self) -> None:
        self.push_screen(AddTransactionScreen(), self._handle_add_transaction)

    def _handle_add_transaction(
        self, result: tuple[datetime, str, int, int, int] | None
    ) -> None:
        if result is None:
            return
        date, desc, credit, debit, amount = result
        try:
            self.manager.add_transaction(date, desc, credit, debit, amount)
            self.manager.generate_ledger()
            self._populate_tree()
            self._populate_table()
            self.notify("Transaction added", severity="information")
        except ValueError as e:
            self.notify(str(e), severity="error")

    def action_refresh(self) -> None:
        self.manager.generate_ledger()
        self._populate_tree()
        self._populate_table()
        self.notify("Refreshed", severity="information")


def main() -> None:
    app = LedgerApp()
    app.run()


if __name__ == "__main__":
    main()
