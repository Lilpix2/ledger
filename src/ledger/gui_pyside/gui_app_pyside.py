"""
PySide6 main application window for the double-entry ledger system.

``LedgerGUI`` is a ``QMainWindow`` subclass that provides the full
accounting interface: account tree, journal table, portfolio view,
menus, filter bar, and status bar.

Layout::

    +------------------------ Menu bar ------------------------+
    | [File] [Accounts] [Transactions] [Help]                   |
    +-----------------------------------------------------------+
    |  Tab widget: [Ledger] [Portfolio]                         |
    |  +------------------+-----------------------------------+ |
    |  | Account tree     | Journal table                     | |
    |  | (QTreeView)      | (QTableView)                      | |
    |  +------------------+-----------------------------------+ |
    +-----------------------------------------------------------+
    |  Status bar: Equation status / Net worth                   |
    +-----------------------------------------------------------+
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenuBar,
    QPushButton, QSplitter, QStatusBar, QTabWidget, QTableView,
    QTreeView, QVBoxLayout, QWidget,
)

from ledger.controllers.accounts import AccountManager
from ledger.gui_pyside.widgets import format_cents
from ledger.constants import DATE_STR


# ── Table models ────────────────────────────────────────────────────


class LedgerTableModel(QAbstractTableModel):
    """Table model for journal transactions (date, description, amount)."""

    def __init__(self, manager: AccountManager, parent: Any = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._transactions: list[tuple[str, str, str]] = []
        self._filters: dict[str, Any] = {}

    def set_filters(self, **kwargs: Any) -> None:
        self._filters = kwargs
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self._transactions = []
        for txn_id, txn in self._manager.journal.transactions.items():
            total = sum(s.amount for s in txn.splits if s.amount > 0)
            self._transactions.append((
                txn.date.strftime(DATE_STR),
                txn.description[:60],
                format_cents(total),
            ))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._transactions)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 3

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._transactions[index.row()][index.column()]
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ["Date", "Description", "Amount"][section]
        return None


class PortfolioTableModel(QAbstractTableModel):
    """Table model for portfolio holdings."""

    def __init__(self, manager: AccountManager, parent: Any = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._holdings: list[tuple[str, str, float, int, int, int, int, float]] = []
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self._holdings = []
        for bid, brokerage in self._manager.accounts.items():
            if brokerage.acct_type != "ASSET":
                continue
            if brokerage.account_subtype not in ("brokerage", "mesp", "retirement"):
                continue
            for holding in self._manager.get_holdings(bid):
                cost = holding.cost_basis_cents
                price = self._manager.get_price(holding.ticker, "latest")
                if price is None:
                    continue
                mkt_val = int(holding.shares * price)
                pnl = mkt_val - cost
                pnl_pct = ((pnl / cost) * 100) if cost else 0.0
                self._holdings.append((
                    brokerage.name, holding.ticker,
                    holding.shares, cost, price,
                    mkt_val, pnl, pnl_pct,
                ))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._holdings)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 8

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            val = self._holdings[index.row()][index.column()]
            if isinstance(val, float):
                return f"{val:.2f}"
            if isinstance(val, int):
                return format_cents(val)
            return str(val)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        headers = ["Account", "Ticker", "Shares", "Cost", "Price",
                    "Market Val", "P&L", "P&L %"]
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return headers[section]
        return None


# ── Budget table model ──────────────────────────────────────────────


class BudgetTableModel(QAbstractTableModel):
    """Table model for budget vs actual display.

    Columns: Account, Budget, Actual, Remaining, Used %.
    """

    HEADERS = ["Account", "Budget", "Actual", "Remaining", "Used %"]

    def __init__(self, manager: AccountManager, month: str = "", parent: Any = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._month = month
        self._data: list[dict] = []

    def set_month(self, month: str) -> None:
        """Change the selected month and refresh data."""
        self._month = month
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        if self._month:
            self._data = self._manager.budget_vs_actual(self._month)
        else:
            self._data = []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 5

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            row = self._data[index.row()]
            if index.column() == 0:
                return row["name"]
            elif index.column() == 4:
                return f"{row['pct_used']:.1f}%"
            else:
                key = ["budget", "actual", "remaining"][index.column() - 1]
                return format_cents(row[key])
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None


# ── Main window ─────────────────────────────────────────────────────


class LedgerGUI(QMainWindow):
    """Main application window for the double-entry ledger system."""

    def __init__(self, db_path: str = "") -> None:
        super().__init__()
        if isinstance(db_path, AccountManager):
            self._manager = db_path
        else:
            self._manager = AccountManager(db_path)
        self._manager.generate_ledger()
        self._init_window()
        self._build_menu()
        self._build_status_bar()
        self._build_central()

    def _init_window(self) -> None:
        self.setWindowTitle("Ledger — Double-Entry Accounting")
        self.resize(1200, 700)
        self._manager.generate_ledger()

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # ── File ──
        file_menu = menubar.addMenu("File")
        refresh_action = file_menu.addAction("Refresh")
        refresh_action.triggered.connect(lambda: self._on_toolbar("Refresh"))
        close_month_action = file_menu.addAction("Close Month…")
        close_month_action.triggered.connect(self._close_month)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.triggered.connect(self.close)

        # ── Accounts ──
        accounts_menu = menubar.addMenu("Accounts")
        new_acct_action = accounts_menu.addAction("New Account…")
        new_acct_action.triggered.connect(lambda: self._on_toolbar("New Account"))

        # ── Transactions ──
        txn_menu = menubar.addMenu("Transactions")
        new_txn_action = txn_menu.addAction("New Transaction…")
        new_txn_action.triggered.connect(lambda: self._on_toolbar("New Transaction"))
        txn_menu.addSeparator()

        inc_stmt = txn_menu.addAction("Income Statement")
        inc_stmt.triggered.connect(self._show_income_stmt)
        bal_sheet = txn_menu.addAction("Balance Sheet")
        bal_sheet.triggered.connect(self._show_balance_sheet)
        net_worth = txn_menu.addAction("Net Worth")
        net_worth.triggered.connect(self._show_net_worth)

        # ── Help ──
        help_menu = menubar.addMenu("Help")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._show_about)

    def _build_status_bar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._refresh_status()

    def _refresh_status(self) -> None:
        eq = self._manager.check_accounting_equation()
        assets = format_cents(eq["assets"])
        liabilities = format_cents(eq["liabilities"])
        net_worth = format_cents(eq["net_worth"])
        bal = "✓" if eq["balanced"] else "✗"
        self._status.showMessage(
            f"{bal}  Assets: {assets}  |  Liabilities: {liabilities}"
            f"  |  Net Worth: {net_worth}"
        )

    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ── Tabs ──
        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        layout.addWidget(self._tabs)

        self._build_ledger_tab()
        self._build_portfolio_tab()
        self._build_budget_tab()

    def _build_ledger_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self._tabs.addTab(tab, "Ledger")

        # ── Toolbar ──
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)

        for text in ["New Account", "New Transaction", "Refresh"]:
            btn = QPushButton(text)
            btn.setObjectName(text.replace(" ", ""))
            btn.clicked.connect(lambda checked, t=text: self._on_toolbar(t))
            toolbar_layout.addWidget(btn)
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        # ── Splitter: tree | table ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Account tree
        self._tree = QTreeView()
        self._tree.setObjectName("accountTree")
        self._tree_model = self._build_tree_model()
        self._tree.setModel(self._tree_model)
        splitter.addWidget(self._tree)

        # Transaction table
        self._table = QTableView()
        self._table.setObjectName("transactionTable")
        self._table_model = LedgerTableModel(self._manager)
        self._table_model.refresh()
        self._table.setModel(self._table_model)
        self._table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self._table)

        splitter.setSizes([300, 700])
        layout.addWidget(splitter)

    def _build_tree_model(self) -> Any:
        from PySide6.QtGui import QStandardItemModel, QStandardItem

        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Account", "Balance"])

        tree = self._manager.build_tree()
        rows = []

        def _walk(parent_id: int, parent_item: Any = None) -> None:
            for cid in sorted(tree.get(parent_id, [])):
                acct = self._manager.accounts.get(cid)
                if not acct or not acct.name:
                    continue
                bal = format_cents(self._manager.get_display_balance(cid))
                item = QStandardItem(f"{acct.name} ({acct.acct_type})")
                item.setEditable(False)
                bal_item = QStandardItem(bal)
                bal_item.setEditable(False)

                if parent_item is None:
                    model.appendRow([item, bal_item])
                else:
                    parent_item.appendRow([item, bal_item])
                _walk(cid, item)

        _walk(0)
        return model

    def _build_portfolio_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._tabs.addTab(tab, "Portfolio")

        # Summary
        self._port_summary = QLabel("")
        self._port_summary.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._port_summary)

        # Table
        self._portfolio_table = QTableView()
        self._portfolio_table.setObjectName("portfolioTable")
        self._port_model = PortfolioTableModel(self._manager)
        self._portfolio_table.setModel(self._port_model)
        self._portfolio_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._portfolio_table)

        self._refresh_portfolio()

    def _build_budget_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._tabs.addTab(tab, "Budgets")

        # ── Month selector ──
        month_layout = QHBoxLayout()
        month_layout.addWidget(QLabel("Month:"))
        self._budget_month_combo = QComboBox()
        self._budget_month_combo.setObjectName("budgetMonthCombo")
        months = sorted(set(m for _, m, _ in self._manager.get_budgets()))
        self._budget_month_combo.addItems(months)
        month_layout.addWidget(self._budget_month_combo)
        month_layout.addStretch()
        layout.addLayout(month_layout)

        # ── Summary label ──
        self._budget_summary = QLabel("")
        self._budget_summary.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._budget_summary)

        # ── Table ──
        self._budget_table = QTableView()
        self._budget_table.setObjectName("budgetTable")
        initial_month = months[0] if months else ""
        self._budget_model = BudgetTableModel(self._manager, initial_month)
        self._budget_table.setModel(self._budget_model)
        self._budget_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._budget_table)

        # ── Wire combo ──
        self._budget_month_combo.currentIndexChanged.connect(self._on_budget_month_change)

        # ── Initial load ──
        self._refresh_budget()

    def _on_budget_month_change(self) -> None:
        self._refresh_budget()

    def _refresh_budget(self) -> None:
        month = self._budget_month_combo.currentText()
        self._budget_model.set_month(month)
        total_budget = sum(
            row["budget"] for row in self._budget_model._data
        )
        total_actual = sum(
            row["actual"] for row in self._budget_model._data
        )
        self._budget_summary.setText(
            f"Total Budgeted: {format_cents(total_budget)}  |  "
            f"Total Actual: {format_cents(total_actual)}"
        )

    def _refresh_portfolio(self) -> None:
        self._port_model.refresh()
        total_mv = sum(h[5] for h in self._port_model._holdings)
        self._port_summary.setText(
            f"Total Market Value: {format_cents(total_mv)}"
        )

    def _close_month(self) -> None:
        """Close temporary accounts for the month.

        Prompts for confirmation, then calls close_temps() on the backend
        and refreshes the UI.
        """
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self, "Close Month",
            "Close temporary accounts for this month?\n\n"
            "Income and expense accounts will be zeroed and "
            "their balances transferred to Retained Earnings.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._manager.close_temps()
            self._manager.generate_ledger()
            self._refresh_all_internal()
            eq = self._manager.check_accounting_equation()
            if eq["balanced"]:
                self._status.showMessage("✓ Month closed — Balanced")
            else:
                self._status.showMessage(f"✗ Unbalanced: {eq}")

    def _on_toolbar(self, action: str) -> None:
        if action == "New Account":
            self._dialog_new_account()
        elif action == "New Transaction":
            self._dialog_new_transaction()
        elif action == "Refresh":
            self._refresh_all_internal()

    def _refresh_all_internal(self) -> None:
        self._manager.generate_ledger()
        self._table_model.refresh()
        self._tree_model = self._build_tree_model()
        self._tree.setModel(self._tree_model)
        self._refresh_status()
        self._refresh_portfolio()
        self._refresh_budget()

    def _refresh_tree(self) -> None:
        """Rebuild the account tree model from scratch."""
        self._refresh_all_internal()

    def _dialog_new_account(self) -> None:
        from ledger.gui_pyside.dialogs import AccountDialog
        dlg = AccountDialog(self._manager, self._on_dialog_success)
        dlg.exec()

    def _dialog_new_transaction(self) -> None:
        from ledger.gui_pyside.dialogs import TransactionDialog
        dlg = TransactionDialog(self._manager, self._on_dialog_success)
        dlg.exec()

    def _on_dialog_success(self) -> None:
        self._refresh_all_internal()

    # ── Reports ────────────────────────────────────────────

    def _show_report(self, report_func_name: str) -> None:
        import ledger.gui_pyside.reports as reports_mod
        report_func = getattr(reports_mod, report_func_name, None)
        if report_func:
            report_func(self, self._manager)

    def _show_income_stmt(self) -> None:
        import ledger.gui_pyside.reports as reports_mod
        reports_mod.show_income_stmt(self, self._manager)

    def _show_balance_sheet(self) -> None:
        import ledger.gui_pyside.reports as reports_mod
        reports_mod.show_balance_sheet(self, self._manager)

    def _show_net_worth(self) -> None:
        import ledger.gui_pyside.reports as reports_mod
        reports_mod.show_net_worth(self, self._manager)

    def _show_about(self) -> None:
        import ledger.gui_pyside.reports as reports_mod
        reports_mod.show_about(self)


def main() -> None:
    """Launch the PySide6 ledger GUI."""
    import sys
    import os
    from PySide6.QtWidgets import QApplication
    from ledger.controllers.accounts import AccountManager

    app = QApplication(sys.argv)
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "journal.db")
    manager = AccountManager(db_path)
    window = LedgerGUI(manager)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
