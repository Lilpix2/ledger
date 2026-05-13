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
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenuBar,
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
        self._transactions: list[tuple[int, str, str, str]] = []
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
                txn_id,
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


# ── Main window ─────────────────────────────────────────────────────


class LedgerGUI(QMainWindow):
    """Main application window for the double-entry ledger system."""

    def __init__(self, db_path: str = "") -> None:
        super().__init__()
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

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Refresh")
        file_menu.addSeparator()
        file_menu.addAction("Quit")

        accounts_menu = menubar.addMenu("Accounts")
        accounts_menu.addAction("New Account...")

        txn_menu = menubar.addMenu("Transactions")
        txn_menu.addAction("New Transaction...")
        txn_menu.addSeparator()
        txn_menu.addAction("Income Statement")
        txn_menu.addAction("Balance Sheet")

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About")

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

    def _refresh_portfolio(self) -> None:
        self._port_model.refresh()
        total_mv = sum(h[5] for h in self._port_model._holdings)
        self._port_summary.setText(
            f"Total Market Value: {format_cents(total_mv)}"
        )

    def _on_toolbar(self, action: str) -> None:
        if action == "Refresh":
            self._manager.generate_ledger()
            self._table_model.refresh()
            self._tree_model = self._build_tree_model()
            self._tree.setModel(self._tree_model)
            self._refresh_status()
            self._refresh_portfolio()

    def _refresh_tree(self) -> None:
        """Rebuild the account tree model from scratch."""
        self._tree_model = self._build_tree_model()
        self._tree.setModel(self._tree_model)
