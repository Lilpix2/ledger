"""Component tests: CRUD access from the main window.

Contracts (written before implementation):
  1. Account tree has a right-click context menu with Edit/Delete
  2. Transaction table has a right-click context menu with Edit/Delete
  3. Accounts menu has "Edit Account…" and "Delete Account…" actions
  4. Transactions menu has "Edit Transaction…" and "Delete Transaction…" actions
  5. Edit opens the corresponding dialog in edit mode
  6. Delete opens confirmation (or deletes for transactions)
  7. LedgerTableModel exposes txn_id_at_row() for lookup
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QTabWidget, QTreeView, QTableView,
        QComboBox, QMenu, QMessageBox, QDialog,
    )
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt, QPoint, QModelIndex
    from PySide6.QtGui import QAction
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.gui_pyside.gui_app_pyside import LedgerGUI, LedgerTableModel

from .conftest import find_widget, click_button


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _get_menu_action_texts(window: LedgerGUI, menu_label: str) -> list[str]:
    """Return non-separator action texts under a menu."""
    texts: list[str] = []
    menubar = window.menuBar()
    for menu_action in menubar.actions():
        if menu_action.text() == menu_label:
            menu = menu_action.menu()
            if menu:
                for action in menu.actions():
                    if not action.isSeparator():
                        texts.append(action.text())
    return texts


def _find_menu_action(window: LedgerGUI, menu_label: str, action_text: str) -> QAction | None:
    """Find a QAction by menu name and action text."""
    menubar = window.menuBar()
    for menu_action in menubar.actions():
        if menu_action.text() == menu_label:
            menu = menu_action.menu()
            if menu:
                for action in menu.actions():
                    if not action.isSeparator() and action.text() == action_text:
                        return action
    return None


# ═══════════════════════════════════════════════════════════════════
#  LedgerTableModel — txn_id lookup
# ═══════════════════════════════════════════════════════════════════


class TestLedgerTableModelTxnLookup:
    """LedgerTableModel must expose txn_id_at_row() for CRUD lookups."""

    def test_txn_id_at_row_returns_int(self, qt_app, fast_seeded):
        """Valid row returns a non-negative integer txn ID."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        if model.rowCount() > 0:
            tid = model.txn_id_at_row(0)
            assert tid is not None
            assert isinstance(tid, int)
            assert tid >= 0

    def test_txn_id_at_row_out_of_range(self, qt_app, fast_seeded):
        """Out-of-range row returns None."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        assert model.txn_id_at_row(-1) is None
        assert model.txn_id_at_row(9999) is None

    def test_txn_id_at_row_empty_model(self, qt_app, fast_manager):
        """Empty model returns None for any row."""
        model = LedgerTableModel(fast_manager)
        model.refresh()
        assert model.rowCount() == 0
        assert model.txn_id_at_row(0) is None

    def test_txn_id_roundtrip(self, qt_app, fast_seeded):
        """txn_id_at_row matches the actual transaction in the journal."""
        model = LedgerTableModel(fast_seeded)
        model.refresh()
        if model.rowCount() > 0:
            tid = model.txn_id_at_row(0)
            assert tid in fast_seeded.journal.transactions
            txn = fast_seeded.journal.transactions[tid]
            assert txn.description[:60] == model.data(model.index(0, 1))


# ═══════════════════════════════════════════════════════════════════
#  Account tree — context menu
# ═══════════════════════════════════════════════════════════════════


class TestAccountTreeContextMenu:
    """Right-click on account tree shows Edit/Delete context menu."""

    def test_context_menu_shows_on_right_click(self, qt_app, fast_seeded):
        """Right-clicking a tree item opens a QMenu with Edit/Delete."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            tree = window.findChild(QTreeView, "accountTree")
            assert tree is not None

            # Select the first non-root item
            model = tree.model()
            items_found = False
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                if model.data(idx) and model.rowCount(idx) > 0:
                    tree.setCurrentIndex(idx)
                    items_found = True
                    break
            assert items_found, "No expandable tree items found"

            # Right-click should trigger context menu
            with patch.object(window, '_show_account_context_menu') as mock:
                # Simulate right-click by emitting the signal
                menu_point = QPoint(10, 10)
                tree.customContextMenuRequested.emit(menu_point)
                QApplication.processEvents()

            mock.assert_called_once_with(menu_point)
        finally:
            window.close()

    def test_context_menu_edit_account_dispatches_dialog(self, qt_app, fast_seeded):
        """Selecting 'Edit Account' from context menu calls _edit_account."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            tree = window.findChild(QTreeView, "accountTree")
            model = tree.model()

            # Select an account
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                if model.data(idx) and model.rowCount(idx) > 0:
                    tree.setCurrentIndex(idx)
                    break

            # Trigger context menu and simulate clicking Edit
            with patch.object(window, '_edit_account') as mock:
                menu = window._build_account_context_menu()
                assert menu is not None
                for action in menu.actions():
                    if "Edit" in action.text():
                        action.trigger()
                        break

            mock.assert_called_once()
        finally:
            window.close()

    def test_context_menu_delete_account_dispatches_dialog(self, qt_app, fast_seeded):
        """Selecting 'Delete Account' from context menu calls _delete_account."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            tree = window.findChild(QTreeView, "accountTree")
            model = tree.model()

            # Select an account
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                if model.data(idx) and model.rowCount(idx) > 0:
                    tree.setCurrentIndex(idx)
                    break

            with patch.object(window, '_delete_account') as mock:
                menu = window._build_account_context_menu()
                assert menu is not None
                for action in menu.actions():
                    if "Delete" in action.text():
                        action.trigger()
                        break

            mock.assert_called_once()
        finally:
            window.close()

    def test_context_menu_edit_opens_dialog(self, qt_app, fast_seeded):
        """_edit_account opens AccountDialog in edit mode."""
        from ledger.gui_pyside.dialogs import AccountDialog
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            tree = window.findChild(QTreeView, "accountTree")
            model = tree.model()

            # Select an account
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                if model.data(idx):
                    tree.setCurrentIndex(idx)
                    break

            with patch.object(AccountDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
                window._edit_account()
                mock_exec.assert_called_once()
        finally:
            window.close()

    def test_context_menu_delete_opens_dialog(self, qt_app, fast_seeded):
        """_delete_account opens DeleteAccountDialog."""
        from ledger.gui_pyside.dialogs import DeleteAccountDialog
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            # Create a throwaway leaf account to delete
            aid = fast_seeded.add_account("DeleteMeLeaf", 1)
            fast_seeded.generate_ledger()
            window._refresh_all_internal()
            QApplication.processEvents()

            tree = window.findChild(QTreeView, "accountTree")
            model = tree.model()

            # Find "DeleteMeLeaf" in the tree and select it
            # Walk the tree to find the new account
            def _find_item(parent_idx):
                for r in range(model.rowCount(parent_idx)):
                    idx = model.index(r, 0, parent_idx)
                    txt = model.data(idx)
                    if txt and "DeleteMeLeaf" in txt:
                        return idx
                    child = _find_item(idx)
                    if child is not None:
                        return child
                return None

            target = _find_item(QModelIndex())
            assert target is not None, "DeleteMeLeaf not found in tree"
            tree.setCurrentIndex(target)
            QApplication.processEvents()

            with patch.object(DeleteAccountDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
                window._delete_account()
                mock_exec.assert_called_once()
        finally:
            window.close()

    def test_no_selection_no_crash(self, qt_app, fast_seeded):
        """Right-click with no selection doesn't crash."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            tree = window.findChild(QTreeView, "accountTree")
            tree.clearSelection()

            # Should not crash
            menu = window._build_account_context_menu()
            assert menu is not None
        finally:
            window.close()


# ═══════════════════════════════════════════════════════════════════
#  Transaction table — context menu
# ═══════════════════════════════════════════════════════════════════


class TestTransactionTableContextMenu:
    """Right-click on transaction table shows Edit/Delete context menu."""

    def test_context_menu_shows_on_right_click(self, qt_app, fast_seeded):
        """Right-clicking a table row opens a QMenu with Edit/Delete."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            assert table is not None

            # Select first row
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(window, '_show_txn_context_menu') as mock:
                menu_point = QPoint(10, 10)
                table.customContextMenuRequested.emit(menu_point)
                QApplication.processEvents()

            mock.assert_called_once_with(menu_point)
        finally:
            window.close()

    def test_context_menu_edit_dispatches(self, qt_app, fast_seeded):
        """Edit Transaction dispatches to _edit_transaction."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(window, '_edit_transaction') as mock:
                menu = window._build_txn_context_menu()
                assert menu is not None
                for action in menu.actions():
                    if "Edit" in action.text():
                        action.trigger()
                        break

            mock.assert_called_once()
        finally:
            window.close()

    def test_context_menu_delete_dispatches(self, qt_app, fast_seeded):
        """Delete Transaction dispatches to _delete_transaction."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(window, '_delete_transaction') as mock:
                menu = window._build_txn_context_menu()
                assert menu is not None
                for action in menu.actions():
                    if "Delete" in action.text():
                        action.trigger()
                        break

            mock.assert_called_once()
        finally:
            window.close()

    def test_edit_transaction_opens_dialog(self, qt_app, fast_seeded):
        """_edit_transaction opens TransactionDialog in edit mode."""
        from ledger.gui_pyside.dialogs import TransactionDialog
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(TransactionDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
                window._edit_transaction()
                mock_exec.assert_called_once()
        finally:
            window.close()

    def test_delete_transaction_with_confirm(self, qt_app, fast_seeded):
        """_delete_transaction prompts then removes from backend."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            txn_count_before = len(window._manager.journal.transactions)

            # Patch QMessageBox.question to return Yes
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                window._delete_transaction()
                QApplication.processEvents()

            txn_count_after = len(window._manager.journal.transactions)
            assert txn_count_after == txn_count_before - 1
        finally:
            window.close()

    def test_delete_transaction_cancel_does_nothing(self, qt_app, fast_seeded):
        """_delete_transaction with No response leaves data unchanged."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            txn_count_before = len(window._manager.journal.transactions)

            with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
                window._delete_transaction()
                QApplication.processEvents()

            assert len(window._manager.journal.transactions) == txn_count_before
        finally:
            window.close()

    def test_no_selection_no_crash(self, qt_app, fast_seeded):
        """_edit_transaction with no selection doesn't crash."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.clearSelection()
            # Should not raise
            window._edit_transaction()
            window._delete_transaction()
        finally:
            window.close()

    def test_delete_keeps_equation_balanced(self, qt_app, fast_seeded):
        """After deleting a transaction, the accounting equation holds."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                window._delete_transaction()
                window._manager.generate_ledger()
                window._refresh_all_internal()
                QApplication.processEvents()

            eq = window._manager.check_accounting_equation()
            assert eq["balanced"]
        finally:
            window.close()

    def test_edit_prepopulates_fields(self, qt_app, fast_seeded):
        """_edit_transaction dialog receives pre-populated txn data."""
        from ledger.gui_pyside.dialogs import TransactionDialog
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            model = table.model()
            tid = model.txn_id_at_row(0)
            assert tid is not None
            txn = window._manager.journal.transactions[tid]

            dialog = TransactionDialog(window._manager, MagicMock(), edit_txn=txn, edit_txn_id=tid)
            assert dialog.windowTitle() == "Edit Transaction"
            assert dialog._edit_txn is txn
            assert dialog._edit_txn_id == tid
            dialog.close()
        finally:
            window.close()

    def test_delete_stale_transaction_id_graceful(self, qt_app, fast_seeded):
        """_delete_transaction handles stale IDs without crashing."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            table = window.findChild(QTableView, "transactionTable")
            table.selectRow(0)
            QApplication.processEvents()

            # Get the selected txn id
            tid = window.selected_txn_id
            assert tid is not None

            # Delete it directly from the manager (simulating stale state)
            window._manager.delete_transaction(tid)

            # Now try to delete through GUI — should not crash
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                window._delete_transaction()
                QApplication.processEvents()

            # No crash = pass
        finally:
            window.close()


# ═══════════════════════════════════════════════════════════════════
#  Menu bar — Edit/Delete actions
# ═══════════════════════════════════════════════════════════════════


class TestMenuCrudActions:
    """Menu bar has Edit/Delete actions under Accounts and Transactions."""

    def test_accounts_menu_has_edit(self, qt_app, fast_seeded):
        """Accounts menu contains 'Edit Account…'."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Accounts")
        assert "Edit Account…" in texts, f"Missing in Accounts: {texts}"
        window.close()

    def test_accounts_menu_has_delete(self, qt_app, fast_seeded):
        """Accounts menu contains 'Delete Account…'."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Accounts")
        assert "Delete Account…" in texts, f"Missing in Accounts: {texts}"
        window.close()

    def test_accounts_crud_order(self, qt_app, fast_seeded):
        """Accounts menu order: New, Edit, Delete."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Accounts")
        assert texts.index("New Account…") < texts.index("Edit Account…")
        assert texts.index("Edit Account…") < texts.index("Delete Account…")
        window.close()

    def test_transactions_menu_has_edit(self, qt_app, fast_seeded):
        """Transactions menu contains 'Edit Transaction…'."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Transactions")
        assert "Edit Transaction…" in texts, f"Missing in Transactions: {texts}"
        window.close()

    def test_transactions_menu_has_delete(self, qt_app, fast_seeded):
        """Transactions menu contains 'Delete Transaction…'."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Transactions")
        assert "Delete Transaction…" in texts, f"Missing in Transactions: {texts}"
        window.close()

    def test_transactions_crud_order(self, qt_app, fast_seeded):
        """Transactions menu order: New, Edit, Delete, separator, reports."""
        window = LedgerGUI(fast_seeded)
        texts = _get_menu_action_texts(window, "Transactions")
        assert texts.index("New Transaction…") < texts.index("Edit Transaction…")
        assert texts.index("Edit Transaction…") < texts.index("Delete Transaction…")
        window.close()

    def test_accounts_edit_menu_triggers_method(self, qt_app, fast_seeded):
        """Accounts → Edit Account… calls _edit_account."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_edit_account') as mock:
            window._act_edit_account.trigger()
        mock.assert_called_once()
        window.close()

    def test_accounts_delete_menu_triggers_method(self, qt_app, fast_seeded):
        """Accounts → Delete Account… calls _delete_account."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_delete_account') as mock:
            window._act_delete_account.trigger()
        mock.assert_called_once()
        window.close()

    def test_transactions_edit_menu_triggers_method(self, qt_app, fast_seeded):
        """Transactions → Edit Transaction… calls _edit_transaction."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_edit_transaction') as mock:
            window._act_edit_txn.trigger()
        mock.assert_called_once()
        window.close()

    def test_transactions_delete_menu_triggers_method(self, qt_app, fast_seeded):
        """Transactions → Delete Transaction… calls _delete_transaction."""
        window = LedgerGUI(fast_seeded)
        with patch.object(window, '_delete_transaction') as mock:
            window._act_delete_txn.trigger()
        mock.assert_called_once()
        window.close()
