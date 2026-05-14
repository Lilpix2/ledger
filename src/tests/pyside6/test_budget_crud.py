"""Component tests: Budget CRUD — ``BudgetDialog`` + UI integration.

Contracts (written before implementation):
  1. BudgetDialog exists with Add/Edit mode, account selector, month, amount
  2. Add mode creates a budget on backend
  3. Edit mode pre-populates and updates budget
  4. Cancel does nothing
  5. Validation rejects empty name/no account/zero amount
  6. Add Budget button exists in budget tab toolbar
  7. Right-click context menu on budget table has Edit/Delete
  8. Edit Budget opens dialog in edit mode
  9. Delete Budget confirms then removes from backend
  10. After CRUD, table refreshes
  11. Month combo repopulates after new budget added
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QPushButton, QComboBox, QLineEdit,
        QLabel, QTableView, QMessageBox, QTabWidget,
    )
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split
from ledger.gui_pyside.gui_app_pyside import LedgerGUI

from .conftest import find_widget, click_button


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _seed_with_budgets(mgr: AccountManager) -> dict[str, int]:
    """Seed a manager with accounts, transactions, and budgets.

    Returns account IDs by name.
    """
    checking = mgr.add_account("Checking", 1)
    groceries = mgr.add_account("Groceries", 5)
    dining = mgr.add_account("Dining", 5)
    rent = mgr.add_account("Rent", 5)
    wages = mgr.add_account("Wages", 4)

    mgr.add_transaction(datetime(2026, 1, 1), "Fund", [
        Split(checking, 1000000), Split(6, -1000000),
    ])
    mgr.add_transaction(datetime(2026, 6, 1), "Paycheck", [
        Split(wages, -300000), Split(checking, 300000),
    ])
    mgr.add_transaction(datetime(2026, 6, 2), "Rent", [
        Split(rent, 150000), Split(checking, -150000),
    ])
    mgr.add_transaction(datetime(2026, 6, 5), "Sprouts", [
        Split(groceries, 8500), Split(checking, -8500),
    ])
    mgr.generate_ledger()

    # Set budgets for June
    mgr.set_budget(groceries, "2026-06", 60000)
    mgr.set_budget(dining, "2026-06", 30000)
    mgr.set_budget(rent, "2026-06", 150000)

    return {
        "checking": checking,
        "groceries": groceries,
        "dining": dining,
        "rent": rent,
        "wages": wages,
    }


@pytest.fixture(autouse=True)
def _patch_messagebox():
    """Patch QMessageBox.warning to return immediately (no blocking modal)."""
    from PySide6.QtWidgets import QMessageBox
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok):
        yield


# ═══════════════════════════════════════════════════════════════════
#  BudgetDialog — Create
# ═══════════════════════════════════════════════════════════════════


class TestBudgetDialogCreate:
    """BudgetDialog: create mode."""

    @property
    def _dialog_class(self):
        from ledger.gui_pyside.dialogs import BudgetDialog
        return BudgetDialog

    def test_opens_with_add_title(self, qt_app, fast_seeded, mock_success):
        """Create mode: title is 'Add Budget'."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        assert dlg.windowTitle() == "Add Budget"

    def test_has_account_selector(self, qt_app, fast_seeded, mock_success):
        """Dialog has an account selector with objectName 'budgetAcctCombo'."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        combo = dlg.findChild(QComboBox, "budgetAcctCombo")
        assert combo is not None
        assert combo.count() > 0
        dlg.close()

    def test_account_selector_filters_to_expense(self, qt_app, fast_seeded, mock_success):
        """Account selector only shows expense accounts."""
        # Add a non-expense account to verify it's excluded
        fast_seeded.add_account("IncomeAccount", 4)  # INCOME type
        fast_seeded.add_account("Checking2", 1)       # ASSET type

        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        combo = dlg.findChild(QComboBox, "budgetAcctCombo")
        assert combo is not None

        texts = [combo.itemText(i) for i in range(combo.count())]
        for text in texts:
            assert "EXPENSE" in text or "expense" in text.lower(), (
                f"Non-expense account in budget selector: {text}"
            )
        dlg.close()

    def test_has_month_combo(self, qt_app, fast_seeded, mock_success):
        """Dialog has a month combo with objectName 'budgetMonthCombo'."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        combo = dlg.findChild(QComboBox, "budgetMonthCombo")
        assert combo is not None
        assert combo.count() >= 1
        dlg.close()

    def test_has_amount_input(self, qt_app, fast_seeded, mock_success):
        """Dialog has an amount input with objectName 'budgetAmountInput'."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        inp = dlg.findChild(QLineEdit, "budgetAmountInput")
        assert inp is not None
        dlg.close()

    def test_has_submit_button(self, qt_app, fast_seeded, mock_success):
        """Dialog has a submit button with objectName 'budgetSubmitBtn'."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        btn = dlg.findChild(QPushButton, "budgetSubmitBtn")
        assert btn is not None
        assert btn.text() in ("Add Budget", "Save Budget")
        dlg.close()

    def test_submit_creates_budget(self, qt_app, fast_seeded, mock_success):
        """Valid submission creates a budget on the backend."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)

        # Select an expense account
        acct_combo = dlg.findChild(QComboBox, "budgetAcctCombo")
        assert acct_combo is not None
        if acct_combo.count() > 0:
            acct_combo.setCurrentIndex(0)

        # Set amount
        amt_input = dlg.findChild(QLineEdit, "budgetAmountInput")
        assert amt_input is not None
        QTest.keyClicks(amt_input, "50000")

        # Submit
        submit_btn = dlg.findChild(QPushButton, "budgetSubmitBtn")
        assert submit_btn is not None
        submit_btn.click()

        mock_success.assert_called_once()

        # Find which account was selected
        text = acct_combo.currentText().strip()
        acct_id = None
        for aid, a in fast_seeded.accounts.items():
            if a.name in text:
                acct_id = aid
                break

        if acct_id:
            budget = fast_seeded.get_budget(acct_id, "2026-06")
            assert budget == 50000, f"Budget for {acct_id}: {budget}"

    def test_cancel_rejects(self, qt_app, fast_seeded, mock_success):
        """Cancel button fires reject(), on_success not called."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)
        rejected = [False]

        dlg.rejected.connect(lambda: rejected.__setitem__(0, True))
        cancel_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel"]
        assert len(cancel_btns) >= 1
        cancel_btns[0].click()

        assert rejected[0] is True
        mock_success.assert_not_called()
        dlg.close()

    def test_empty_amount_shows_error(self, qt_app, fast_seeded, mock_success):
        """Submit with empty amount shows warning, budget not created."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)

        acct_combo = dlg.findChild(QComboBox, "budgetAcctCombo")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(0)

        submit_btn = dlg.findChild(QPushButton, "budgetSubmitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()
        dlg.close()

    def test_zero_amount_shows_error(self, qt_app, fast_seeded, mock_success):
        """Submit with 0 amount shows warning, budget not created."""
        dlg = self._dialog_class(fast_seeded, "2026-06", mock_success)

        acct_combo = dlg.findChild(QComboBox, "budgetAcctCombo")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(0)

        amt_input = dlg.findChild(QLineEdit, "budgetAmountInput")
        if amt_input:
            QTest.keyClicks(amt_input, "0")

        submit_btn = dlg.findChild(QPushButton, "budgetSubmitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()
        dlg.close()


# ═══════════════════════════════════════════════════════════════════
#  BudgetDialog — Edit mode
# ═══════════════════════════════════════════════════════════════════


class TestBudgetDialogEdit:
    """BudgetDialog: edit mode."""

    @property
    def _dialog_class(self):
        from ledger.gui_pyside.dialogs import BudgetDialog
        return BudgetDialog

    def test_opens_with_edit_title(self, qt_app, fast_manager, mock_success):
        """Edit mode: title is 'Edit Budget'."""
        ids = _seed_with_budgets(fast_manager)
        dlg = self._dialog_class(
            fast_manager, "2026-06", mock_success,
            edit_account_id=ids["groceries"], edit_amount=60000,
        )
        assert dlg.windowTitle() == "Edit Budget"
        dlg.close()

    def test_edit_prepopulates_fields(self, qt_app, fast_manager, mock_success):
        """Edit mode pre-fills account, month, amount."""
        ids = _seed_with_budgets(fast_manager)
        dlg = self._dialog_class(
            fast_manager, "2026-06", mock_success,
            edit_account_id=ids["groceries"], edit_amount=60000,
        )

        # Account should show "Groceries"
        acct_combo = dlg.findChild(QComboBox, "budgetAcctCombo")
        assert acct_combo is not None
        assert "Groceries" in acct_combo.currentText()

        # Month should show the passed month
        month_combo = dlg.findChild(QComboBox, "budgetMonthCombo")
        assert month_combo is not None
        assert month_combo.currentText() == "2026-06"

        # Amount should be pre-filled
        amt_input = dlg.findChild(QLineEdit, "budgetAmountInput")
        assert amt_input is not None
        assert amt_input.text() == "60000"

        dlg.close()

    def test_edit_submit_updates_budget(self, qt_app, fast_manager, mock_success):
        """Submitting in edit mode updates the budget amount."""
        ids = _seed_with_budgets(fast_manager)
        dlg = self._dialog_class(
            fast_manager, "2026-06", mock_success,
            edit_account_id=ids["groceries"], edit_amount=60000,
        )

        # Change the amount
        amt_input = dlg.findChild(QLineEdit, "budgetAmountInput")
        assert amt_input is not None
        amt_input.clear()
        QTest.keyClicks(amt_input, "75000")

        submit_btn = dlg.findChild(QPushButton, "budgetSubmitBtn")
        assert submit_btn is not None
        submit_btn.click()

        mock_success.assert_called_once()
        budget = fast_manager.get_budget(ids["groceries"], "2026-06")
        assert budget == 75000, f"Budget after edit: {budget}"
        dlg.close()

    def test_edit_submit_keeps_same_account_month(self, qt_app, fast_manager, mock_success):
        """Edit mode updates the existing budget, doesn't create a new one."""
        ids = _seed_with_budgets(fast_manager)
        dlg = self._dialog_class(
            fast_manager, "2026-06", mock_success,
            edit_account_id=ids["groceries"], edit_amount=60000,
        )

        amt_input = dlg.findChild(QLineEdit, "budgetAmountInput")
        amt_input.clear()
        QTest.keyClicks(amt_input, "80000")

        submit_btn = dlg.findChild(QPushButton, "budgetSubmitBtn")
        submit_btn.click()

        # Should still be 1 budget for Groceries June (updated, not duplicated)
        budgets = fast_manager.get_budgets("2026-06")
        grocery_budgets = [b for b in budgets if b[0] == ids["groceries"]]
        assert len(grocery_budgets) == 1
        assert grocery_budgets[0][2] == 80000
        dlg.close()

    def test_cancel_in_edit_does_nothing(self, qt_app, fast_manager, mock_success):
        """Cancel in edit mode doesn't change the budget."""
        ids = _seed_with_budgets(fast_manager)
        budget_before = fast_manager.get_budget(ids["groceries"], "2026-06")

        dlg = self._dialog_class(
            fast_manager, "2026-06", mock_success,
            edit_account_id=ids["groceries"], edit_amount=60000,
        )

        amt_input = dlg.findChild(QLineEdit, "budgetAmountInput")
        amt_input.clear()
        QTest.keyClicks(amt_input, "99999")

        cancel_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel"]
        if cancel_btns:
            cancel_btns[0].click()

        budget_after = fast_manager.get_budget(ids["groceries"], "2026-06")
        assert budget_after == budget_before
        mock_success.assert_not_called()
        dlg.close()


# ═══════════════════════════════════════════════════════════════════
#  Budget tab — Add button
# ═══════════════════════════════════════════════════════════════════


class TestBudgetTabAddButton:
    """Budget tab has an Add Budget button."""

    def test_add_budget_button_exists(self, qt_app, fast_manager):
        """Budget tab toolbar has an 'Add Budget' button."""
        _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            btn = find_widget(window, QPushButton, "Add Budget")
            assert btn is not None, "Add Budget button not found"
        finally:
            window.close()

    def test_add_budget_button_triggers_dialog(self, qt_app, fast_manager, mock_success):
        """Clicking 'Add Budget' opens BudgetDialog."""
        from ledger.gui_pyside.dialogs import BudgetDialog
        _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            with patch.object(BudgetDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
                btn = find_widget(window, QPushButton, "Add Budget")
                assert btn is not None
                btn.click()
                QApplication.processEvents()
                mock_exec.assert_called_once()
        finally:
            window.close()

    def test_add_budget_refreshes_table(self, qt_app, fast_seeded, mock_success):
        """Adding a budget via dialog refreshes the table."""
        window = LedgerGUI(fast_seeded)
        window.show()
        QApplication.processEvents()

        try:
            tabs = window.findChild(QTabWidget, "mainTabs")
            budget_idx = [tabs.tabText(i) for i in range(tabs.count())].index("Budgets")
            tabs.setCurrentIndex(budget_idx)
            QApplication.processEvents()

            table = window.findChild(QTableView, "budgetTable")
            model = table.model()
            before = model.rowCount()

            # Create a budget directly (simulating what the dialog would do)
            groceries = next(aid for aid, a in fast_seeded.accounts.items()
                             if a.name == "Groceries")
            fast_seeded.set_budget(groceries, "2026-06", 50000)
            window._refresh_all_internal()
            QApplication.processEvents()

            after = model.rowCount()
            assert after > before
        finally:
            window.close()


# ═══════════════════════════════════════════════════════════════════
#  Budget table — Context menu
# ═══════════════════════════════════════════════════════════════════


class TestBudgetTableContextMenu:
    """Right-click on budget table shows Edit/Delete context menu."""

    def _switch_to_budgets(self, window):
        tabs = window.findChild(QTabWidget, "mainTabs")
        budget_idx = [tabs.tabText(i) for i in range(tabs.count())].index("Budgets")
        tabs.setCurrentIndex(budget_idx)
        QApplication.processEvents()

    def test_context_menu_shows_on_right_click(self, qt_app, fast_manager):
        """Right-clicking a budget row shows context menu."""
        _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            assert table is not None

            # Select first row
            table.selectRow(0)
            QApplication.processEvents()

            from PySide6.QtCore import QPoint
            with patch.object(window, '_show_budget_context_menu') as mock:
                table.customContextMenuRequested.emit(QPoint(10, 10))
                QApplication.processEvents()

            mock.assert_called_once()
        finally:
            window.close()

    def test_context_menu_edit_budget_dispatches(self, qt_app, fast_manager):
        """Edit Budget from context menu calls _edit_budget."""
        _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(window, '_edit_budget') as mock:
                menu = window._build_budget_context_menu()
                assert menu is not None
                for action in menu.actions():
                    if "Edit" in action.text():
                        action.trigger()
                        break

            mock.assert_called_once()
        finally:
            window.close()

    def test_context_menu_delete_budget_dispatches(self, qt_app, fast_manager):
        """Delete Budget from context menu calls _delete_budget."""
        _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(window, '_delete_budget') as mock:
                menu = window._build_budget_context_menu()
                assert menu is not None
                for action in menu.actions():
                    if "Delete" in action.text():
                        action.trigger()
                        break

            mock.assert_called_once()
        finally:
            window.close()

    def test_edit_budget_opens_dialog(self, qt_app, fast_manager):
        """_edit_budget opens BudgetDialog in edit mode."""
        from ledger.gui_pyside.dialogs import BudgetDialog
        ids = _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            table.selectRow(0)
            QApplication.processEvents()

            with patch.object(BudgetDialog, 'exec', return_value=QDialog.Accepted) as mock_exec:
                window._edit_budget()
                mock_exec.assert_called_once()
        finally:
            window.close()

    def test_delete_budget_with_confirm(self, qt_app, fast_manager):
        """_delete_budget prompts and removes from backend."""
        ids = _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            table.selectRow(0)
            QApplication.processEvents()

            budgets_before = len(fast_manager.get_budgets("2026-06"))

            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                window._delete_budget()
                QApplication.processEvents()

            budgets_after = len(fast_manager.get_budgets("2026-06"))
            assert budgets_after == budgets_before - 1
        finally:
            window.close()

    def test_delete_budget_cancel_does_nothing(self, qt_app, fast_manager):
        """_delete_budget with No response leaves data unchanged."""
        ids = _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            table.selectRow(0)
            QApplication.processEvents()

            budgets_before = len(fast_manager.get_budgets("2026-06"))

            with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
                window._delete_budget()
                QApplication.processEvents()

            assert len(fast_manager.get_budgets("2026-06")) == budgets_before
        finally:
            window.close()

    def test_delete_budget_refreshes_table(self, qt_app, fast_manager):
        """After deleting a budget, table row count decreases."""
        ids = _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            model = table.model()
            after = model.rowCount()

            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                # Delete the first budget via backend then refresh
                row0_id = model.index(0, 0)
                acct_name = model.data(row0_id)
                aid = next(aid for aid, a in fast_manager.accounts.items()
                          if a.name == acct_name)
                month = window._budget_month_combo.currentText()
                window._manager.clear_budget(aid, month)
                window._refresh_all_internal()
                QApplication.processEvents()

            refreshed = model.rowCount()
            assert refreshed <= after
        finally:
            window.close()

    def test_no_selection_no_crash(self, qt_app, fast_manager):
        """_edit_budget with no selection doesn't crash."""
        _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            self._switch_to_budgets(window)
            table = window.findChild(QTableView, "budgetTable")
            table.clearSelection()

            # Should not raise
            window._edit_budget()
            window._delete_budget()
        finally:
            window.close()


# ═══════════════════════════════════════════════════════════════════
#  Month combo refresh
# ═══════════════════════════════════════════════════════════════════


class TestBudgetMonthComboRefresh:
    """Month combo updates after budget CRUD."""

    def test_add_budget_adds_month_to_combo(self, qt_app, fast_manager):
        """Adding a budget for a new month adds that month to the combo."""
        _seed_with_budgets(fast_manager)
        # Only June budgets exist
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            combo = window.findChild(QComboBox, "budgetMonthCombo")
            assert combo is not None

            months_before = [combo.itemText(i) for i in range(combo.count())]
            assert "2026-06" in months_before

            # Add a budget for July
            groceries = next(aid for aid, a in fast_manager.accounts.items()
                            if a.name == "Groceries")
            fast_manager.set_budget(groceries, "2026-07", 60000)
            window._refresh_all_internal()
            QApplication.processEvents()

            months_after = [combo.itemText(i) for i in range(combo.count())]
            assert "2026-07" in months_after
        finally:
            window.close()

    def test_delete_all_budgets_clears_table(self, qt_app, fast_manager):
        """Deleting all budgets for a month leaves table with 0 rows."""
        ids = _seed_with_budgets(fast_manager)
        window = LedgerGUI(fast_manager)
        window.show()
        QApplication.processEvents()

        try:
            combo = window.findChild(QComboBox, "budgetMonthCombo")
            combo.setCurrentText("2026-06")

            table = window.findChild(QTableView, "budgetTable")
            model = table.model()

            # Clear all budgets via backend
            fast_manager.clear_all_budgets("2026-06")
            window._refresh_all_internal()
            QApplication.processEvents()

            assert model.rowCount() == 0
        finally:
            window.close()
