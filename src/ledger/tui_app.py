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
from .models.data_class import Split


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


class AddAccountScreen(ModalScreen[tuple[str, int, str | None] | None]):
    """Modal for creating a new account.

    Returns (name, parent_id, account_subtype) or None.
    """

    def compose(self) -> ComposeResult:
        yield Static("── Add Account ──", id="title")
        with Vertical(id="parent-selector"):
            yield Static("Select parent account by clicking a node:", id="sel-hint")
            yield Tree("root", id="parent-tree")
        yield Static("", id="selected-parent")
        yield Input(placeholder="Account name", id="acct-name")
        yield Input(placeholder="Or type parent ID", id="acct-parent")
        yield Input(
            placeholder="Subtype (optional): checking, credit_card, brokerage, mesp, retirement",
            id="acct-subtype",
        )
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

    @on(Input.Changed, "#acct-subtype")
    def _validate_subtype(self, event: Input.Changed) -> None:
        value = event.value.strip().lower()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        from ..constants import ACCOUNT_SUBTYPES
        _set_valid(w, value in ACCOUNT_SUBTYPES)

    # ── Actions ─────────────────────────────────────

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        name = self.query_one("#acct-name", Input).value.strip()
        parent_str = self.query_one("#acct-parent", Input).value.strip()
        subtype = self.query_one("#acct-subtype", Input).value.strip().lower() or None

        if not name:
            self.query_one("#acct-name", Input).value = "Name is required"
            return
        if not parent_str.isnumeric():
            self.query_one("#acct-parent", Input).value = "Must be a number"
            return
        parent = int(parent_str)
        self.dismiss((name, parent, subtype))

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


# ── Modal: Add Transaction ─────────────────────────────────────────


class AddTransactionScreen(ModalScreen[tuple[datetime, str, list] | None]):
    """Modal for creating a compound journal entry with N splits."""

    def __init__(self):
        super().__init__()
        self.split_count = 0

    def compose(self) -> ComposeResult:
        yield Static("── Add Transaction ──", id="title")
        yield Input(placeholder="Filter accounts by name...", id="acct-filter")
        yield DataTable(id="acct-table")

        with Horizontal(id="date-row"):
            yield Input(
                placeholder="MM-DD-YYYY H:M:S",
                id="txn-date",
                value=datetime.now().strftime(DATE_STR),
            )
            yield Button("\U0001f4c5", id="cal-btn", variant="default")

        yield Input(placeholder="Description", id="txn-desc")

        with Horizontal(classes="split-header"):
            yield Label("Splits:", classes="section-label")
            yield Button("+ Add Split", id="add-split-btn")

        with VerticalScroll(id="split-rows"):
            yield from self._build_split_row(0)

        self.split_count = 1

        with Horizontal(id="buttons"):
            yield Button("Submit", variant="primary", id="submit")
            yield Button("Cancel", id="cancel")

    def _build_split_row(self, idx, acct="", amt="", is_debit=True):
        """Yield the widgets for one split row."""
        with Horizontal(classes="split-row", id=f"split-{idx}"):
            yield Input(
                placeholder="Acct#", value=acct,
                id=f"split-acct-{idx}", classes="split-acct",
            )
            yield Input(
                placeholder="Amount (cents)", value=amt,
                id=f"split-amt-{idx}", classes="split-amt",
            )
            yield Button(
                "D" if is_debit else "C",
                id=f"split-dir-{idx}",
                classes="split-dir",
                variant="primary" if is_debit else "default",
            )
            if idx > 0:
                yield Button("\u2716", id=f"split-rmv-{idx}", classes="split-rmv")

    def _add_split_row(self):
        idx = self.split_count
        container = self.query_one("#split-rows", VerticalScroll)
        for widget in self._build_split_row(idx):
            container.mount(widget)
        self.split_count += 1
        self._scroll_bottom()

    def _scroll_bottom(self):
        try:
            self.query_one("#split-rows", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def on_mount(self):
        self._populate_table()
        self.query_one("#txn-date", Input).focus()

    def _populate_table(self, query=""):
        table = self.query_one("#acct-table", DataTable)
        table.clear()
        table.add_columns("ID", "Name", "Type")
        table.zebra_stripes = True
        table.cursor_type = "row"
        q = query.strip().lower()
        accounts = self.app.manager.accounts
        for acct_id, acct in sorted(accounts.items()):
            if acct_id == 0:
                continue
            if q and q not in acct.name.lower():
                continue
            table.add_row(str(acct_id), acct.name, acct.acct_type, key=str(acct_id))

    # ── Split management ─────────────────────────────────────

    @on(Button.Pressed, "#add-split-btn")
    def _handle_add_split(self):
        self._add_split_row()

    # ── Real-time validation ─────────────────────────────────

    @on(Input.Changed, "#txn-date")
    def _validate_date(self, event):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        try:
            datetime.strptime(value, DATE_STR)
            _set_valid(w, True)
        except ValueError:
            _set_valid(w, False)

    @on(Input.Changed, ".split-acct")
    def _validate_split_acct(self, event):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        account_ids = set(self.app.manager.accounts.keys())
        _set_valid(w, _valid_account_id(value, account_ids))

    @on(Input.Changed, ".split-amt")
    def _validate_split_amt(self, event):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        _set_valid(w, value.lstrip("-").isnumeric() and int(value) != 0)

    # ── Direction toggle ────────────────────────────────────

    @on(Button.Pressed, ".split-dir")
    def _toggle_split_dir(self, event):
        btn = event.button
        if btn.label == "D":
            btn.label = "C"
            btn.variant = "default"
        else:
            btn.label = "D"
            btn.variant = "primary"

    # ── Filter / Row selection ──────────────────────────────

    @on(Input.Changed, "#acct-filter")
    def _filter_accounts(self, event):
        self._populate_table(event.value.strip())

    @on(DataTable.RowSelected, "#acct-table")
    def _select_account_row(self, event):
        acct_id = str(event.row_key)
        focused = self.screen.focused
        if focused is None or "split-acct" not in (focused.id or ""):
            return
        focused.value = acct_id
        _set_valid(focused, True)

    # ── Calendar ────────────────────────────────────────────

    @on(Button.Pressed, "#cal-btn")
    def _open_calendar(self):
        def _handle_date(selected):
            if selected is not None:
                self.query_one("#txn-date", Input).value = selected.strftime(DATE_STR)
        self.app.push_screen(DatePickerModal(), _handle_date)

    # ── Submit / Cancel ─────────────────────────────────────

    @on(Button.Pressed, "#submit")
    def submit(self):
        date_str = self.query_one("#txn-date", Input).value.strip()
        desc = self.query_one("#txn-desc", Input).value.strip()
        if not all([date_str, desc]):
            self.notify("Date and description required", severity="error")
            return
        try:
            date = datetime.strptime(date_str, DATE_STR)
        except ValueError:
            self.query_one("#txn-date", Input).value = "Bad date format"
            return

        splits = []
        for i in range(self.split_count):
            acct_input = self.query_one(f"#split-acct-{i}", Input)
            amt_input = self.query_one(f"#split-amt-{i}", Input)
            dir_btn = self.query_one(f"#split-dir-{i}", Button)
            acct_str = acct_input.value.strip()
            amt_str = amt_input.value.strip()
            if not acct_str or not amt_str:
                self.notify(f"Split {i+1}: fill in both account and amount", severity="error")
                return
            if not acct_str.isnumeric():
                self.notify(f"Split {i+1}: account must be a number", severity="error")
                return
            try:
                amt = int(amt_str)
            except ValueError:
                self.notify(f"Split {i+1}: amount must be a number (cents)", severity="error")
                return
            if amt == 0:
                self.notify(f"Split {i+1}: amount cannot be zero", severity="error")
                return
            is_debit = dir_btn.label == "D"
            splits.append(Split(
                account_id=int(acct_str),
                amount=amt if is_debit else -amt,
            ))
        if len(splits) < 2:
            self.notify("Need at least 2 splits", severity="error")
            return
        total = sum(s.amount for s in splits)
        if total != 0:
            self.notify(f"Unbalanced: debits and credits differ by {total} cents", severity="error")
            return
        self.dismiss((date, desc, splits))

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(None)

# ── Modal: Buy / Sell (Investment Transaction) ──────────────────────


class BuySellScreen(ModalScreen[dict | None]):
    """Modal for a buy/sell investment transaction.

    Returns a dict with keys:
    - direction: "buy" or "sell"
    - investment_id: account ID (brokerage/mesp/retirement)
    - cash_id: funding/destination account
    - ticker: str
    - shares: float
    - price_cents: int per share
    - date: datetime
    - description: str
    - gain_account_id: int or None (sells only)
    """

    def compose(self) -> ComposeResult:
        yield Static("── Buy / Sell ──", id="title")

        yield Static("Direction:", classes="field-label")
        with Horizontal(id="dir-row"):
            yield Button("Buy", id="dir-buy", variant="primary")
            yield Button("Sell", id="dir-sell", variant="default")

        yield Static("Investment account (brokerage/mesp/retirement):", classes="field-label")
        with Horizontal(id="inv-row"):
            yield Input(placeholder="Account ID", id="inv-acct", classes="acct-input")
            yield Button("Pick", id="inv-pick", variant="default")

        yield Static("Cash account (source / destination):", classes="field-label")
        with Horizontal(id="cash-row"):
            yield Input(placeholder="Account ID", id="cash-acct", classes="acct-input")
            yield Button("Pick", id="cash-pick", variant="default")

        with Horizontal(id="date-row"):
            yield Input(
                placeholder="Date: " + DATE_STR,
                id="txn-date",
                value=datetime.now().strftime(DATE_STR),
            )
            yield Button("\U0001f4c5", id="cal-btn", variant="default")

        yield Input(placeholder="Description", id="txn-desc")

        with Horizontal(id="ticker-row"):
            yield Input(placeholder="Ticker (e.g. AAPL)", id="ticker", classes="half-input")
            yield Input(placeholder="Shares", id="shares", classes="half-input")

        with Horizontal(id="price-row"):
            yield Static("$", id="price-symbol")
            yield Input(placeholder="Price per share in cents", id="price", classes="half-input")

        yield Static("Gains account (optional, sells only):", id="gain-label", classes="field-label")
        with Horizontal(id="gain-row"):
            yield Input(placeholder="Account ID or leave blank", id="gain-acct", classes="acct-input")

        with Horizontal(id="buttons"):
            yield Button("Submit", variant="primary", id="submit")
            yield Button("Cancel", id="cancel")

        # Account picker datatable (hidden until pick is clicked)
        yield DataTable(id="acct-picker", classes="picker-table", zebra_stripes=True)

    def on_mount(self):
        self._direction = "buy"
        self.query_one("#acct-picker", DataTable).visible = False
        self.query_one("#gain-row", Horizontal).visible = False
        self.query_one("#gain-label", Static).visible = False
        self.query_one("#txn-date", Input).focus()

    # ── Direction toggle ────────────────────────────────

    @on(Button.Pressed, "#dir-buy")
    def _set_buy(self):
        self._direction = "buy"
        self.query_one("#dir-buy", Button).variant = "primary"
        self.query_one("#dir-sell", Button).variant = "default"
        self.query_one("#gain-row", Horizontal).visible = False
        self.query_one("#gain-label", Static).visible = False

    @on(Button.Pressed, "#dir-sell")
    def _set_sell(self):
        self._direction = "sell"
        self.query_one("#dir-sell", Button).variant = "primary"
        self.query_one("#dir-buy", Button).variant = "default"
        self.query_one("#gain-row", Horizontal).visible = True
        self.query_one("#gain-label", Static).visible = True

    # ── Account picker modal within modal ───────────────

    def _show_picker(self, target_id: str):
        """Show the account picker table, filtered to relevant acct types."""
        self._picker_target = target_id
        table = self.query_one("#acct-picker", DataTable)
        table.clear()
        table.add_columns("ID", "Name", "Type", "Subtype")
        table.zebra_stripes = True
        table.cursor_type = "row"

        manager = self.app.manager
        for acct_id, acct in sorted(manager.accounts.items()):
            if acct_id == 0:
                continue
            subtype = acct.account_subtype or ""
            table.add_row(
                str(acct_id), acct.name, acct.acct_type, subtype,
                key=str(acct_id),
            )

        table.visible = True
        table.focus()

    @on(Button.Pressed, "#inv-pick")
    def _pick_investment(self):
        self._show_picker("inv-acct")

    @on(Button.Pressed, "#cash-pick")
    def _pick_cash(self):
        self._show_picker("cash-acct")

    @on(DataTable.RowSelected, "#acct-picker")
    def _picker_row_selected(self, event: DataTable.RowSelected):
        acct_id = str(event.row_key)
        target = self.query_one(f"#{self._picker_target}", Input)
        target.value = acct_id
        self.query_one("#acct-picker", DataTable).visible = False

    # ── Validation ──────────────────────────────────────

    @on(Input.Changed, ".acct-input")
    def _validate_acct_input(self, event: Input.Changed):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        account_ids = set(self.app.manager.accounts.keys())
        _set_valid(w, value.isnumeric() and int(value) in account_ids)

    @on(Input.Changed, "#txn-date")
    def _validate_date(self, event: Input.Changed):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        try:
            datetime.strptime(value, DATE_STR)
            _set_valid(w, True)
        except ValueError:
            _set_valid(w, False)

    @on(Input.Changed, "#shares")
    def _validate_shares(self, event: Input.Changed):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        try:
            f = float(value)
            _set_valid(w, f > 0)
        except ValueError:
            _set_valid(w, False)

    @on(Input.Changed, "#price")
    def _validate_price(self, event: Input.Changed):
        value = event.value.strip()
        w = event.input
        if not value:
            w.remove_class("valid", "invalid")
            return
        _set_valid(w, value.lstrip("-").isnumeric() and int(value) > 0)

    # ── Calendar ────────────────────────────────────────

    @on(Button.Pressed, "#cal-btn")
    def _open_calendar(self):
        def _handle_date(selected):
            if selected is not None:
                self.query_one("#txn-date", Input).value = selected.strftime(DATE_STR)
        self.app.push_screen(DatePickerModal(), _handle_date)

    # ── Submit / Cancel ─────────────────────────────────

    @on(Button.Pressed, "#submit")
    def submit(self):
        date_str = self.query_one("#txn-date", Input).value.strip()
        desc = self.query_one("#txn-desc", Input).value.strip()
        ticker = self.query_one("#ticker", Input).value.strip().upper()
        shares_str = self.query_one("#shares", Input).value.strip()
        price_str = self.query_one("#price", Input).value.strip()
        inv_str = self.query_one("#inv-acct", Input).value.strip()
        cash_str = self.query_one("#cash-acct", Input).value.strip()

        if not all([date_str, desc, ticker, shares_str, price_str, inv_str, cash_str]):
            self.notify("All required fields must be filled", severity="error")
            return

        try:
            date = datetime.strptime(date_str, DATE_STR)
        except ValueError:
            self.notify("Invalid date format", severity="error")
            return

        try:
            shares = float(shares_str)
        except ValueError:
            self.notify("Shares must be a number", severity="error")
            return

        try:
            price_cents = int(price_str)
        except ValueError:
            self.notify("Price must be in whole cents", severity="error")
            return

        try:
            inv_id = int(inv_str)
            cash_id = int(cash_str)
        except ValueError:
            self.notify("Account IDs must be numbers", severity="error")
            return

        gain_id = None
        if self._direction == "sell":
            gain_str = self.query_one("#gain-acct", Input).value.strip()
            if gain_str:
                try:
                    gain_id = int(gain_str)
                except ValueError:
                    self.notify("Gains account ID must be a number", severity="error")
                    return

        self.dismiss({
            "direction": self._direction,
            "investment_id": inv_id,
            "cash_id": cash_id,
            "ticker": ticker,
            "shares": shares,
            "price_cents": price_cents,
            "date": date,
            "description": desc,
            "gain_account_id": gain_id,
        })

    @on(Button.Pressed, "#cancel")
    def cancel(self):
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

    AddTransactionScreen #acct-filter {
        margin: 0 0 1 0;
    }

    AddTransactionScreen #acct-table {
        height: 10;
        margin: 0 0 1 0;
        border: solid $foreground 10%;
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

    /* ── Buy/Sell Modal ─────────────────────────── */
    BuySellScreen {
        align: center middle;
    }

    BuySellScreen > #title {
        text-style: bold;
        padding: 0 0 1 0;
        width: 100%;
        content-align: center middle;
    }

    BuySellScreen .field-label {
        height: 1;
        padding: 0 0 0 0;
        text-style: italic;
        margin: 0 0 0 0;
    }

    BuySellScreen Input {
        margin: 0 0 1 0;
    }

    BuySellScreen .acct-input {
        width: 80%;
        margin: 0 0 1 0;
    }

    BuySellScreen .half-input {
        width: 50%;
        margin: 0 0 1 0;
    }

    BuySellScreen #dir-row {
        height: 3;
        margin: 0 0 1 0;
    }

    BuySellScreen #dir-row > Button {
        width: 20;
        margin: 0 1 0 0;
    }

    BuySellScreen #inv-row,
    BuySellScreen #cash-row,
    BuySellScreen #gain-row {
        height: 3;
        margin: 0 0 0 0;
    }

    BuySellScreen #inv-row > Button,
    BuySellScreen #cash-row > Button,
    BuySellScreen #gain-row > Button {
        width: 10;
        margin: 0 0 0 1;
    }

    BuySellScreen #ticker-row,
    BuySellScreen #price-row {
        height: 3;
        margin: 0 0 0 0;
    }

    BuySellScreen #price-symbol {
        width: 2;
        content-align: center middle;
        margin: 0 0 1 0;
    }

    BuySellScreen .picker-table {
        height: 10;
        border: solid $primary;
        margin: 1 0 0 0;
    }

    BuySellScreen > #buttons {
        align: center middle;
        margin: 1 0 0 0;
    }

    BuySellScreen Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("a", "add_account", "Add Account"),
        Binding("t", "add_transaction", "Add Transaction"),
        Binding("i", "income_statement", "Income Stmt"),
        Binding("r", "retained_earnings", "RE Stmt"),
        Binding("b", "balance_sheet", "Balance Sheet"),
        Binding("s", "account_summary", "Summary"),
        Binding("n", "net_worth", "Net Worth"),
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
                subtype_tag = f" [{account.account_subtype}]" if account.account_subtype else ""
                label = (
                    f"{account.name}  "
                    f"[dim]({account.acct_type}{subtype_tag})[/]  "
                    f"(${balance_cents/100:,.2f})"
                )
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

            subtype_info = f"Subtype: {account.account_subtype}\n" if account.account_subtype else ""
            holding_count = len(account.holdings)
            holdings_info = f"Holdings: {holding_count} positions\n" if holding_count else ""
            msg = (
                f"[bold]{account.name}[/]  [dim]({account.acct_type})[/]\n"
                f"Display balance: ${display_bal/100:,.2f}\n"
                f"Raw balance: ${raw_bal/100:,.2f}\n"
                f"Normal: {direction}\n"
                f"Type: {account.acct_type}\n"
                f"{subtype_info}"
                f"{holdings_info}"
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
                txn_accounts = {s.account_id for s in txn.splits}
                if not txn_accounts & filter_ids:
                    continue

            debits_str = ", ".join(
                f"{self._acct_name(s.account_id)} (${s.amount/100:,.2f})"
                for s in txn.splits if s.amount > 0
            )
            credits_str = ", ".join(
                f"{self._acct_name(s.account_id)} (${-s.amount/100:,.2f})"
                for s in txn.splits if s.amount < 0
            )
            table.add_row(
                txn.date.strftime(DATE_STR),
                txn.description,
                debits_str,
                credits_str,
                f"${txn.total()/100:,.2f}",
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

    def _handle_add_account(self, result: tuple[str, int, str | None] | None) -> None:
        if result is None:
            return
        name, parent, subtype = result
        try:
            self.manager.add_account(name, parent, account_subtype=subtype)
            self.manager.generate_ledger()
            self._populate_tree()
            self._refresh_status()
            subtype_info = f" ({subtype})" if subtype else ""
            self.notify(f"Account '{name}'{subtype_info} created", severity="information")
        except ValueError as e:
            self.notify(str(e), severity="error")

    def action_add_transaction(self) -> None:
        self.push_screen(AddTransactionScreen(), self._handle_add_transaction)

    def action_buy_sell(self) -> None:
        """Open the buy/sell investment modal."""
        self.push_screen(BuySellScreen(), self._handle_buy_sell)

    def _handle_buy_sell(self, result: dict | None) -> None:
        if result is None:
            return

        try:
            if result["direction"] == "buy":
                txn_id = self.manager.buy_security(
                    date=result["date"],
                    description=result["description"],
                    brokerage_id=result["investment_id"],
                    cash_id=result["cash_id"],
                    ticker=result["ticker"],
                    shares=result["shares"],
                    price_cents=result["price_cents"],
                )
                self.notify(
                    f"Bought {result['shares']} × {result['ticker']} "
                    f"(txn #{txn_id})",
                    severity="information",
                )
            else:
                txn_id, realized = self.manager.sell_security(
                    date=result["date"],
                    description=result["description"],
                    brokerage_id=result["investment_id"],
                    cash_id=result["cash_id"],
                    ticker=result["ticker"],
                    shares=result["shares"],
                    price_cents=result["price_cents"],
                    gain_account_id=result.get("gain_account_id"),
                )
                gain_str = f" (realized ${abs(realized)/100:,.2f})" if realized else ""
                self.notify(
                    f"Sold {result['shares']} × {result['ticker']}{gain_str} "
                    f"(txn #{txn_id})",
                    severity="information",
                )

            self.manager.generate_ledger()
            self._populate_tree()
            self._populate_table()
            self._refresh_status()

        except ValueError as e:
            self.notify(str(e), severity="error")

    def _handle_add_transaction(self, result: tuple[datetime, str, list] | None) -> None:
        if result is None:
            return
        date, desc, splits = result
        try:
            self.manager.add_transaction(date, desc, splits)
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

    def action_income_statement(self) -> None:
        report = self.manager.gen_income_report()
        lines = [f"Income: ${report['income_total']/100:,.2f}"]
        for name, total in report["income"]:
            lines.append(f"  {name:20s}  ${total/100:>8,.2f}")
        lines.append(f"Expenses: ${report['expenses_total']/100:,.2f}")
        for name, total in report["expenses"]:
            lines.append(f"  {name:20s}  ${total/100:>8,.2f}")
        ni = report["net_income"]
        label = "Net Income" if ni >= 0 else "Net Loss"
        lines.append("")
        lines.append(f"{label:10s}  ${abs(ni)/100:>8,.2f}")
        self.notify("\n".join(lines), title="Income Statement", timeout=10)

    def action_retained_earnings(self) -> None:
        r = self.manager.gen_retained_earnings_statement()
        lines = [f"Beginning RE:  ${r['beginning_re']/100:>8,.2f}",
                 f"+ Net Income:  ${r['net_income']/100:>8,.2f}"]
        if r["dividends"]:
            lines.append(f"- Dividends:   ${r['dividends']/100:>8,.2f}")
        lines.append("")
        lines.append(f"Ending RE:     ${r['ending_re']/100:>8,.2f}")
        self.notify("\n".join(lines), title="RE Statement", timeout=10)

    def action_balance_sheet(self) -> None:
        bs = self.manager.gen_balance_sheet()
        lines = ["[bold]ASSETS[/]"]
        for name, bal in bs["assets"]:
            lines.append(f"  {name:25s}  ${bal/100:>8,.2f}")
        lines.append(f"  Total: ${bs['total_assets']/100:,.2f}")
        lines.append("")
        lines.append("[bold]LIABILITIES[/]")
        for name, bal in bs["liabilities"]:
            lines.append(f"  {name:25s}  ${bal/100:>8,.2f}")
        lines.append(f"  Total: ${bs['total_liabilities']/100:,.2f}")
        lines.append("")
        lines.append("[bold]EQUITY[/]")
        for name, bal in bs["equity"]:
            lines.append(f"  {name:25s}  ${bal/100:>8,.2f}")
        lines.append(f"  Total: ${bs['total_equity']/100:,.2f}")
        status = "\u2713" if bs["balanced"] else "\u2717 UNBALANCED"
        lines.append(f"")
        lines.append(f"A = L + E: {status}")
        self.notify("\n".join(lines), title="Balance Sheet", timeout=15)

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

    def action_account_summary(self) -> None:
        report = self.manager.gen_account_summary()
        lines = []
        for group in report["groups"]:
            if not group["accounts"]:
                continue
            lines.append(f"[bold]{group['type_label']}[/]")
            for aid, name, bal in group["accounts"]:
                if bal != 0:
                    lines.append(f"  {aid:3d}  {name:20s}  ${bal/100:>8,.2f}")
            total = group["total_cents"]
            lines.append(f"  [dim]{'-' * 32}[/]")
            lines.append(f"  Total {group['type_label']:<15s}  ${total/100:>8,.2f}")
            lines.append("")
        lines.append(f"[bold]Net Worth:  ${report['net_worth']/100:>8,.2f}[/]")
        status = "✓ Balanced" if report["balanced"] else "✗ UNBALANCED"
        lines.append(f"Equation:    {status}")
        self.notify("\n".join(lines), title="Account Summary", timeout=15)


def main() -> None:
    app = LedgerApp()
    app.run()


if __name__ == "__main__":
    main()
