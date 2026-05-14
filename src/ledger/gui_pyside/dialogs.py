"""
PySide6 dialogs for the double-entry ledger system.

Classes
-------
AccountDialog        — Create/edit an account
TransactionDialog    — Create/edit a compound (multi-split) journal entry
BuySellDialog        — Buy or sell a security
DeleteAccountDialog  — Delete an account with reassignment options
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ledger.controllers.accounts import AccountManager
from ledger.constants import ACCOUNT_SUBTYPES, DATE_STR
from ledger.models.data_class import Split, JournalTransaction

from .widgets import AccountSelector, build_account_choices, format_cents


# ═══════════════════════════════════════════════════════════════════
#  AccountDialog
# ═══════════════════════════════════════════════════════════════════


class AccountDialog(QDialog):
    """Modal dialog for creating or editing an account.

    Pass ``edit_acct`` and ``edit_acct_id`` to pre-populate for editing.

    Widgets (accessible via findChild):
        parentCombo     — QComboBox for parent selection
        nameInput       — QLineEdit for account name
        typeCombo       — QComboBox for type override
        subtypeCombo    — QComboBox for optional subtype
        createBtn       — QPushButton (Save/Create)
    """

    def __init__(
        self,
        manager: AccountManager,
        on_success: Callable[[], None],
        edit_acct: Any | None = None,
        edit_acct_id: int | None = None,
    ) -> None:
        super().__init__()
        self._manager = manager
        self._on_success = on_success
        self._edit_acct = edit_acct
        self._edit_acct_id = edit_acct_id

        self.setWindowTitle("Edit Account" if edit_acct else "New Account")
        self.setMinimumWidth(420)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # ── Parent ──
        parent_layout = QHBoxLayout()
        parent_layout.addWidget(QLabel("Parent Account:"))
        self._parent_combo = AccountSelector(
            self._manager, object_name="parentCombo",
        )
        parent_layout.addWidget(self._parent_combo)
        layout.addLayout(parent_layout)

        # ── Name ──
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Account Name:"))
        self._name_input = QLineEdit()
        self._name_input.setObjectName("nameInput")
        if self._edit_acct:
            self._name_input.setText(self._edit_acct.name)
        name_layout.addWidget(self._name_input)
        layout.addLayout(name_layout)

        # ── Subtype ──
        subtype_layout = QHBoxLayout()
        subtype_layout.addWidget(QLabel("Subtype (optional):"))
        self._subtype_combo = QComboBox()
        self._subtype_combo.setObjectName("subtypeCombo")
        self._subtype_combo.addItems(sorted(ACCOUNT_SUBTYPES))
        self._subtype_combo.setCurrentIndex(-1)
        subtype_layout.addWidget(self._subtype_combo)
        layout.addLayout(subtype_layout)

        # ── Type override ──
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type (optional):"))
        self._type_combo = QComboBox()
        self._type_combo.setObjectName("typeCombo")
        self._type_combo.addItems(["", "ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"])
        self._type_combo.setCurrentIndex(0)
        type_layout.addWidget(self._type_combo)
        layout.addLayout(type_layout)

        # ── Hint label ──
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet("color: gray;")
        layout.addWidget(self._hint_label)

        self._parent_combo.currentIndexChanged.connect(self._on_parent_change)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        self._create_btn = QPushButton("Save" if self._edit_acct else "Create")
        self._create_btn.setObjectName("createBtn")
        self._create_btn.clicked.connect(self._submit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self._create_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_parent_change(self) -> None:
        pid = self._parent_combo.selected_id
        if pid is not None and pid in self._manager.accounts:
            p = self._manager.accounts[pid]
            self._hint_label.setText(f"Type will inherit from parent: {p.acct_type}")

    def _submit(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Account name is required")
            self.reject()
            return

        pid = self._parent_combo.selected_id
        if pid is None:
            QMessageBox.warning(self, "Error", "Select a valid parent account")
            self.reject()
            return

        subtype = self._subtype_combo.currentText().strip() or None
        type_text = self._type_combo.currentText().strip() or None

        try:
            if self._edit_acct and self._edit_acct_id is not None:
                self._manager.update_account(
                    self._edit_acct_id, name, pid, type_text, subtype,
                )
            else:
                self._manager.add_account(name, pid, type_text, account_subtype=subtype)
            self._on_success()
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{type(e).__name__}: {e}")
            self.reject()


# ═══════════════════════════════════════════════════════════════════
#  TransactionDialog
# ═══════════════════════════════════════════════════════════════════


class TransactionDialog(QDialog):
    """Modal dialog for creating or editing a compound journal entry.

    Widgets:
        splitTable      — QTableWidget showing splits
        splitAcctCombo  — AccountSelector for split entry
        splitAmountInput — QLineEdit for split amount
        debitCheckbox   — QCheckBox for debit/credit toggle
        addSplitBtn     — QPushButton
        removeSplitBtn  — QPushButton
        submitBtn       — QPushButton
        dateInput       — QLineEdit
        descInput       — QLineEdit
    """

    def __init__(
        self,
        manager: AccountManager,
        on_success: Callable[[], None],
        edit_txn: Any | None = None,
        edit_txn_id: int | None = None,
    ) -> None:
        super().__init__()
        self._manager = manager
        self._on_success = on_success
        self._edit_txn = edit_txn
        self._edit_txn_id = edit_txn_id

        self.setWindowTitle("Edit Transaction" if edit_txn else "New Transaction")
        self.setMinimumSize(600, 450)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._splits: list[dict] = []

        # ── Date ──
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Date:"))
        self._date_input = QLineEdit(
            self._edit_txn.date.strftime(DATE_STR) if self._edit_txn
            else datetime.now().strftime(DATE_STR)
        )
        self._date_input.setObjectName("dateInput")
        date_layout.addWidget(self._date_input)
        layout.addLayout(date_layout)

        # ── Description ──
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self._desc_input = QLineEdit(
            self._edit_txn.description if self._edit_txn else ""
        )
        self._desc_input.setObjectName("descInput")
        desc_layout.addWidget(self._desc_input)
        layout.addLayout(desc_layout)

        # ── Split table ──
        self._split_table = QTableWidget(0, 4)
        self._split_table.setObjectName("splitTable")
        self._split_table.setHorizontalHeaderLabels(["Account", "Debit", "Credit", "Memo"])
        self._split_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._split_table)

        # ── Add split form ──
        add_group = QGroupBox("Add Split")
        add_layout = QHBoxLayout(add_group)

        add_layout.addWidget(QLabel("Account:"))
        self._acct_combo = AccountSelector(
            self._manager, object_name="splitAcctCombo",
        )
        add_layout.addWidget(self._acct_combo)

        add_layout.addWidget(QLabel("Amount:"))
        self._amt_input = QLineEdit()
        self._amt_input.setObjectName("splitAmountInput")
        add_layout.addWidget(self._amt_input)

        self._debit_cb = QCheckBox("Debit")
        self._debit_cb.setObjectName("debitCheckbox")
        self._debit_cb.setChecked(True)
        add_layout.addWidget(self._debit_cb)

        add_layout.addWidget(QLabel("Memo:"))
        memo_input = QLineEdit()
        memo_input.setObjectName("splitMemoInput")
        add_layout.addWidget(memo_input)

        add_btn = QPushButton("Add Split")
        add_btn.setObjectName("addSplitBtn")
        add_btn.clicked.connect(lambda: self._add_split(memo_input))
        add_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("removeSplitBtn")
        remove_btn.clicked.connect(self._remove_split)
        add_layout.addWidget(remove_btn)

        # Auto-tick debit based on account
        self._acct_combo.currentIndexChanged.connect(self._on_acct_change)

        layout.addWidget(add_group)

        # ── Pre-populate splits in edit mode ──
        if self._edit_txn:
            for s in self._edit_txn.splits:
                acct = self._manager.accounts.get(s.account_id)
                name = acct.name if acct else f"ID {s.account_id}"
                row = self._split_table.rowCount()
                self._split_table.insertRow(row)
                self._split_table.setItem(row, 0, QTableWidgetItem(name))
                if s.amount > 0:
                    self._split_table.setItem(row, 1, QTableWidgetItem(str(s.amount)))
                else:
                    self._split_table.setItem(row, 2, QTableWidgetItem(str(-s.amount)))
                self._split_table.setItem(row, 3, QTableWidgetItem(s.memo or ""))

        # ── Submit / Cancel ──
        btn_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        submit_btn.setObjectName("submitBtn")
        submit_btn.clicked.connect(self._submit)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(submit_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_acct_change(self) -> None:
        aid = self._acct_combo.selected_id
        if aid is not None and aid in self._manager.accounts:
            acct = self._manager.accounts[aid]
            self._debit_cb.setChecked(self._manager.is_debit_normal(aid))

    def _add_split(self, memo_input: QLineEdit) -> None:
        aid = self._acct_combo.selected_id
        if aid is None:
            QMessageBox.warning(self, "Error", "Select a valid account")
            return

        try:
            amt = int(self._amt_input.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Amount must be a number (cents)")
            return

        if amt == 0:
            QMessageBox.warning(self, "Error", "Amount cannot be zero")
            return

        memo = memo_input.text()
        acct = self._manager.accounts.get(aid)
        name = acct.name if acct else f"ID {aid}"

        row = self._split_table.rowCount()
        self._split_table.insertRow(row)
        self._split_table.setItem(row, 0, QTableWidgetItem(name))
        if self._debit_cb.isChecked():
            self._split_table.setItem(row, 1, QTableWidgetItem(str(amt)))
        else:
            self._split_table.setItem(row, 2, QTableWidgetItem(str(amt)))
        self._split_table.setItem(row, 3, QTableWidgetItem(memo))

        self._amt_input.clear()
        memo_input.clear()
        self._acct_combo.setFocus()

    def _remove_split(self) -> None:
        row = self._split_table.currentRow()
        if row >= 0:
            self._split_table.removeRow(row)

    def _submit(self) -> None:
        date_str = self._date_input.text().strip()
        desc = self._desc_input.text().strip()
        if not date_str or not desc:
            QMessageBox.warning(self, "Error", "Date and description required")
            return

        try:
            date = datetime.strptime(date_str, DATE_STR)
        except ValueError:
            QMessageBox.warning(
                self, "Error", f"Invalid date format. Use {DATE_STR}",
            )
            return

        name_to_id = {
            acct.name: aid for aid, acct in self._manager.accounts.items()
        }
        splits: list[Split] = []
        for row in range(self._split_table.rowCount()):
            name = self._split_table.item(row, 0).text()
            debit_item = self._split_table.item(row, 1)
            credit_item = self._split_table.item(row, 2)
            memo_item = self._split_table.item(row, 3)
            debit = int(debit_item.text()) if debit_item and debit_item.text() else 0
            credit = int(credit_item.text()) if credit_item and credit_item.text() else 0
            memo = memo_item.text() if memo_item else ""

            aid = name_to_id.get(name)
            if aid is None:
                QMessageBox.warning(self, "Error", f"Unknown account: {name}")
                return
            if debit:
                splits.append(Split(aid, debit, memo))
            if credit:
                splits.append(Split(aid, -credit, memo))

        if len(splits) < 2:
            QMessageBox.warning(self, "Error", "Need at least 2 splits")
            return

        total = sum(s.amount for s in splits)
        if total != 0:
            QMessageBox.warning(
                self, "Error",
                f"Unbalanced: debits and credits differ by {total} cents",
            )
            return

        try:
            if self._edit_txn and self._edit_txn_id is not None:
                self._manager.delete_transaction(self._edit_txn_id)
            self._manager.add_transaction(date, desc, splits)
            self._on_success()
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════════
#  BuySellDialog
# ═══════════════════════════════════════════════════════════════════


class BuySellDialog(QDialog):
    """Modal dialog for buy/sell security transactions.

    Widgets:
        buyRadio            — QRadioButton
        sellRadio           — QRadioButton
        invAccountCombo     — AccountSelector (brokerage/mesp/retirement)
        cashAccountCombo    — AccountSelector
        gainsAccountCombo   — AccountSelector (visible for sells)
        tickerInput         — QLineEdit
        sharesInput         — QLineEdit
        priceInput          — QLineEdit
        dateInput           — QLineEdit
        descInput           — QLineEdit
        submitBtn           — QPushButton
    """

    def __init__(
        self,
        manager: AccountManager,
        on_success: Callable[[], None],
    ) -> None:
        super().__init__()
        self._manager = manager
        self._on_success = on_success
        self.setWindowTitle("Buy / Sell Security")
        self.setMinimumWidth(480)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # ── Direction ──
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Direction:"))
        self._buy_radio = QRadioButton("Buy")
        self._buy_radio.setObjectName("buyRadio")
        self._buy_radio.setChecked(True)
        self._sell_radio = QRadioButton("Sell")
        self._sell_radio.setObjectName("sellRadio")
        dir_layout.addWidget(self._buy_radio)
        dir_layout.addWidget(self._sell_radio)
        layout.addLayout(dir_layout)

        # ── Investment account ──
        inv_layout = QHBoxLayout()
        inv_layout.addWidget(QLabel("Investment Account:"))
        self._inv_combo = AccountSelector(
            self._manager,
            subtype_filter={"brokerage", "mesp", "retirement"},
            object_name="invAccountCombo",
        )
        inv_layout.addWidget(self._inv_combo)
        layout.addLayout(inv_layout)

        # ── Cash account ──
        cash_layout = QHBoxLayout()
        cash_layout.addWidget(QLabel("Cash Account:"))
        self._cash_combo = AccountSelector(
            self._manager, object_name="cashAccountCombo",
        )
        cash_layout.addWidget(self._cash_combo)
        layout.addLayout(cash_layout)

        # ── Gains account (hidden for buy) ──
        self._gains_widget = QWidget()
        gains_layout = QHBoxLayout(self._gains_widget)
        gains_layout.addWidget(QLabel("Gains Account (optional):"))
        self._gains_combo = AccountSelector(
            self._manager, object_name="gainsAccountCombo",
        )
        gains_layout.addWidget(self._gains_combo)
        self._gains_widget.setVisible(False)
        layout.addWidget(self._gains_widget)

        self._sell_radio.toggled.connect(self._on_direction_change)

        # ── Ticker ──
        ticker_layout = QHBoxLayout()
        ticker_layout.addWidget(QLabel("Ticker:"))
        self._ticker_input = QLineEdit()
        self._ticker_input.setObjectName("tickerInput")
        ticker_layout.addWidget(self._ticker_input)
        layout.addLayout(ticker_layout)

        # ── Shares + Price ──
        sp_layout = QHBoxLayout()
        sp_layout.addWidget(QLabel("Shares:"))
        self._shares_input = QLineEdit()
        self._shares_input.setObjectName("sharesInput")
        sp_layout.addWidget(self._shares_input)
        sp_layout.addWidget(QLabel("Price (cents):"))
        self._price_input = QLineEdit()
        self._price_input.setObjectName("priceInput")
        sp_layout.addWidget(self._price_input)
        layout.addLayout(sp_layout)

        # ── Date ──
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Date:"))
        self._date_input = QLineEdit(datetime.now().strftime(DATE_STR))
        self._date_input.setObjectName("dateInput")
        date_layout.addWidget(self._date_input)
        layout.addLayout(date_layout)

        # ── Description ──
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self._desc_input = QLineEdit()
        self._desc_input.setObjectName("descInput")
        desc_layout.addWidget(self._desc_input)
        layout.addLayout(desc_layout)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        submit_btn.setObjectName("submitBtn")
        submit_btn.clicked.connect(self._submit)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(submit_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_direction_change(self) -> None:
        is_sell = self._sell_radio.isChecked()
        self._gains_widget.setVisible(is_sell)

    def _submit(self) -> None:
        direction = "buy" if self._buy_radio.isChecked() else "sell"
        inv_id = self._inv_combo.selected_id
        cash_id = self._cash_combo.selected_id

        if inv_id is None:
            QMessageBox.warning(self, "Error", "Select an investment account")
            return
        if cash_id is None:
            QMessageBox.warning(self, "Error", "Select a cash account")
            return

        ticker = self._ticker_input.text().strip().upper()
        if not ticker:
            QMessageBox.warning(self, "Error", "Ticker required")
            return

        try:
            shares = float(self._shares_input.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Shares must be a number")
            return
        if shares <= 0:
            QMessageBox.warning(self, "Error", "Shares must be positive")
            return

        try:
            price_cents = int(self._price_input.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Price must be in cents")
            return
        if price_cents <= 0:
            QMessageBox.warning(self, "Error", "Price must be positive")
            return

        try:
            date = datetime.strptime(self._date_input.text().strip(), DATE_STR)
        except ValueError:
            QMessageBox.warning(self, "Error", f"Invalid date. Use {DATE_STR}")
            return

        desc = self._desc_input.text().strip() or f"{direction.title()} {shares} × {ticker}"
        gain_id = self._gains_combo.selected_id if direction == "sell" else None

        try:
            if direction == "buy":
                self._manager.buy_security(
                    date, desc, inv_id, cash_id, ticker, shares, price_cents,
                )
            else:
                self._manager.sell_security(
                    date, desc, inv_id, cash_id,
                    ticker, shares, price_cents,
                    gain_account_id=gain_id,
                )
            self._on_success()
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════════
#  DeleteAccountDialog
# ═══════════════════════════════════════════════════════════════════


class DeleteAccountDialog(QDialog):
    """Modal dialog for deleting an account with options.

    When the account has children or referencing transactions, the user
    can choose to reassign them to another account or cascade-delete.

    For accounts with no children and no transactions, the dialog
    performs a simple confirmation and calls ``on_success`` immediately.

    Widgets:
        childGroup          — QGroupBox for sub-account options
        childTargetCombo    — AccountSelector for child reassignment
        childCascadeCheck   — QCheckBox cascade option
        transactionGroup    — QGroupBox for transaction options
        txnTargetCombo      — AccountSelector for txn reassignment
        txnCascadeCheck     — QCheckBox cascade option
        deleteBtn           — QPushButton
        cancelBtn           — QPushButton
    """

    def __init__(
        self,
        manager: AccountManager,
        acct_id: int,
        on_success: Callable[[], None],
    ) -> None:
        super().__init__()
        self._manager = manager
        self._acct_id = acct_id
        self._on_success = on_success

        if acct_id == 0:
            QMessageBox.warning(self, "Error", "Cannot delete root account")
            self.reject()
            return

        acct = self._manager.accounts.get(acct_id)
        if not acct:
            QMessageBox.warning(self, "Error", f"Account ID {acct_id} not found")
            self.reject()
            return

        self._children = [
            (aid, a) for aid, a in self._manager.accounts.items()
            if a.parent == acct_id and aid != 0
        ]
        self._referencing_txn_ids: list[int] = []
        for txn_id, txn in self._manager.journal.transactions.items():
            for s in txn.splits:
                if s.account_id == acct_id:
                    self._referencing_txn_ids.append(txn_id)
                    break

        # Simple path: no children, no transactions
        if not self._children and not self._referencing_txn_ids:
            self._manager.delete_account(acct_id)
            self._on_success()
            self.accept()
            return

        # Full dialog with options
        self.setWindowTitle(f"Delete Account: {acct.name}")
        self.setMinimumWidth(500)
        self._build(acct)

    def _build(self, acct: Any) -> None:
        layout = QVBoxLayout(self)

        # ── Account header ──
        header = QLabel(f"Account: {acct.name} ({acct.acct_type})")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self._child_cascade = False
        self._txn_cascade = False

        # ── Children section ──
        if self._children:
            child_group = QGroupBox("Sub-accounts")
            child_group.setObjectName("childGroup")
            child_layout = QVBoxLayout(child_group)

            child_layout.addWidget(
                QLabel(f"{len(self._children)} sub-account(s) found")
            )

            cascade_cb = QCheckBox("Delete children too")
            cascade_cb.setObjectName("childCascadeCheck")
            child_layout.addWidget(cascade_cb)

            combo_layout = QHBoxLayout()
            combo_layout.addWidget(QLabel("Or move to:"))
            self._child_combo = AccountSelector(
                self._manager, object_name="childTargetCombo",
            )
            combo_layout.addWidget(self._child_combo)
            child_layout.addLayout(combo_layout)

            cascade_cb.toggled.connect(
                lambda checked: self._child_combo.setEnabled(not checked)
            )
            cascade_cb.toggled.connect(lambda checked: setattr(self, '_child_cascade', checked))

            layout.addWidget(child_group)

        # ── Transactions section ──
        if self._referencing_txn_ids:
            txn_group = QGroupBox("Transactions")
            txn_group.setObjectName("transactionGroup")
            txn_layout = QVBoxLayout(txn_group)

            txn_layout.addWidget(
                QLabel(f"{len(self._referencing_txn_ids)} transaction(s) reference this account")
            )

            txn_cascade_cb = QCheckBox("Delete transactions too")
            txn_cascade_cb.setObjectName("txnCascadeCheck")
            txn_layout.addWidget(txn_cascade_cb)

            txn_combo_layout = QHBoxLayout()
            txn_combo_layout.addWidget(QLabel("Or move to:"))
            self._txn_combo = AccountSelector(
                self._manager, object_name="txnTargetCombo",
            )
            txn_combo_layout.addWidget(self._txn_combo)
            txn_layout.addLayout(txn_combo_layout)

            txn_cascade_cb.toggled.connect(
                lambda checked: self._txn_combo.setEnabled(not checked)
            )
            txn_cascade_cb.toggled.connect(
                lambda checked: setattr(self, '_txn_cascade', checked)
            )

            layout.addWidget(txn_group)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        delete_btn = QPushButton("Delete Account")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.clicked.connect(self._do_delete)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _do_delete(self) -> None:
        # Resolve child target
        child_target: int | None = None
        if self._children and not self._child_cascade:
            child_target = self._child_combo.selected_id
            if child_target is None:
                QMessageBox.warning(
                    self, "Error",
                    "Select a target for children or check 'Delete children too'",
                )
                return

        # Resolve txn target
        txn_target: int | None = None
        if self._referencing_txn_ids and not self._txn_cascade:
            txn_target = self._txn_combo.selected_id
            if txn_target is None:
                QMessageBox.warning(
                    self, "Error",
                    "Select a target for transactions or check 'Delete transactions too'",
                )
                return

        try:
            if child_target is not None:
                self._manager.reassign_children(self._acct_id, child_target)
            if txn_target is not None:
                self._manager.reassign_transactions(self._acct_id, txn_target)
            self._manager.delete_account(self._acct_id)
            self._on_success()
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))


# ═══════════════════════════════════════════════════════════════════
#  BudgetDialog
# ═══════════════════════════════════════════════════════════════════


class BudgetDialog(QDialog):
    """Modal dialog for adding or editing a monthly budget.

    Create mode: account selector (expense accounts only), month selector,
    amount input, submit.

    Edit mode: pre-populated fields, updates existing budget.

    Widgets:
        budgetAcctCombo   — QComboBox filtered to EXPENSE accounts
        budgetMonthCombo  — QComboBox with month options
        budgetAmountInput — QLineEdit for amount in cents
        budgetSubmitBtn   — QPushButton (Add Budget / Save Budget)
    """

    def __init__(
        self,
        manager: AccountManager,
        month: str,
        on_success: Callable[[], None],
        edit_account_id: int | None = None,
        edit_amount: int | None = None,
    ) -> None:
        super().__init__()
        self._manager = manager
        self._on_success = on_success
        self._month = month
        self._edit_account_id = edit_account_id
        self._edit_amount = edit_amount
        self._is_edit = edit_account_id is not None

        self.setWindowTitle("Edit Budget" if self._is_edit else "Add Budget")
        self.setMinimumWidth(400)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # ── Account selector ──
        acct_layout = QHBoxLayout()
        acct_layout.addWidget(QLabel("Account:"))
        self._acct_combo = AccountSelector(
            self._manager,
            object_name="budgetAcctCombo",
            acct_type_filter={"EXPENSE"},
        )
        acct_layout.addWidget(self._acct_combo)
        layout.addLayout(acct_layout)

        # ── Month combo ──
        month_layout = QHBoxLayout()
        month_layout.addWidget(QLabel("Month:"))
        self._month_combo = QComboBox()
        self._month_combo.setObjectName("budgetMonthCombo")
        # Populate with months that have budgets, plus the passed month
        all_months = sorted(set(
            m for _, m, _ in self._manager.get_budgets()
        ) | {self._month})
        self._month_combo.addItems(all_months)
        # Select the passed month
        idx = self._month_combo.findText(self._month)
        if idx >= 0:
            self._month_combo.setCurrentIndex(idx)
        month_layout.addWidget(self._month_combo)
        layout.addLayout(month_layout)

        # ── Amount input ──
        amt_layout = QHBoxLayout()
        amt_layout.addWidget(QLabel("Amount (cents):"))
        self._amt_input = QLineEdit()
        self._amt_input.setObjectName("budgetAmountInput")
        if self._edit_amount is not None:
            self._amt_input.setText(str(self._edit_amount))
        amt_layout.addWidget(self._amt_input)
        layout.addLayout(amt_layout)

        # ── Pre-select account in edit mode ──
        if self._edit_account_id is not None:
            self._acct_combo.selected_id = self._edit_account_id
            # Lock the account combo in edit mode
            self._acct_combo.setEnabled(False)
            self._month_combo.setEnabled(False)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        submit_text = "Save Budget" if self._is_edit else "Add Budget"
        self._submit_btn = QPushButton(submit_text)
        self._submit_btn.setObjectName("budgetSubmitBtn")
        self._submit_btn.clicked.connect(self._submit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self._submit_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _submit(self) -> None:
        amt_text = self._amt_input.text().strip()
        if not amt_text:
            QMessageBox.warning(self, "Error", "Amount is required")
            self.reject()
            return

        try:
            amount = int(amt_text)
        except ValueError:
            QMessageBox.warning(self, "Error", "Amount must be a number (cents)")
            self.reject()
            return

        if amount <= 0:
            QMessageBox.warning(self, "Error", "Amount must be positive")
            self.reject()
            return

        acct_id = self._acct_combo.selected_id
        if acct_id is None:
            QMessageBox.warning(self, "Error", "Select a valid account")
            self.reject()
            return

        month = self._month_combo.currentText()
        try:
            self._manager.set_budget(acct_id, month, amount)
            self._on_success()
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{type(e).__name__}: {e}")
            self.reject()
