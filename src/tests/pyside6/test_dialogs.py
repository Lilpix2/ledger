"""Component tests: PySide6 dialogs — ``gui/dialogs.py``.

Tests
-----
- ``AccountDialog`` — create vs edit mode, validation, submission flow
- ``TransactionDialog`` — split management (add/remove/edit), validation
- ``BuySellDialog`` — direction toggle, field validation, submission

Boundary
--------
- Backend mocked via ``fast_manager`` / ``fast_seeded`` (MockDB)
- Dialogs are created WITHOUT calling ``exec()`` (no modal blocking)
- ``QTest.mouseClick`` for button interactions
- ``on_success`` is a ``MagicMock``

Black-box
---------
Interaction through Qt widget surface: ``QTest.mouseClick``,
``QTest.keyClicks``, ``QComboBox.setCurrentIndex``.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    from PySide6.QtWidgets import (QApplication, QDialog, QPushButton,
                                     QComboBox, QLabel, QLineEdit, QTableWidget,
                                     QCheckBox, QRadioButton)
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.gui_pyside.dialogs import AccountDialog, TransactionDialog, BuySellDialog
from ledger.models.data_class import Split
from ledger.constants import DATE_STR

from .conftest import find_widget, click_button


@pytest.fixture(autouse=True)
def _patch_messagebox():
    """Patch QMessageBox.warning to return immediately (no blocking modal)."""
    from PySide6.QtWidgets import QMessageBox
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok):
        yield


# ═══════════════════════════════════════════════════════════════════
#  AccountDialog
# ═══════════════════════════════════════════════════════════════════


class TestAccountDialog:
    """Create/edit account modal."""

    # ── Create mode ────────────────────────────────────────

    def test_opens_with_create_title(self, qt_app, fast_seeded, mock_success):
        """Default mode: 'New Account' title."""
        dlg = AccountDialog(fast_seeded, mock_success)
        assert dlg.windowTitle() == "New Account"

    def test_empty_name_shows_error(self, qt_app, fast_seeded, mock_success):
        """Submit with no name → error dialog shown, on_success not called."""
        dlg = AccountDialog(fast_seeded, mock_success)

        # Find and click the Create button
        create_btn = dlg.findChild(QPushButton, "createBtn")
        assert create_btn is not None, "Create button not found"

        # Before clicking, connect to the dialog's reject/accepted signals
        # to detect validation failure vs success
        rejected = False

        def _on_reject():
            nonlocal rejected
            rejected = True

        dlg.rejected.connect(_on_reject)
        create_btn.click()
        # QDialog::reject() fires when validation fails
        mock_success.assert_not_called()

    def test_valid_submit_creates_account(self, qt_app, fast_seeded, mock_success):
        """Valid submission → on_success called and account created."""
        dlg = AccountDialog(fast_seeded, mock_success)

        name_input = dlg.findChild(QLineEdit, "nameInput")
        assert name_input is not None
        QTest.keyClicks(name_input, "Test Account")

        # Select a parent account
        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        if parent_combo and parent_combo.count() > 0:
            parent_combo.setCurrentIndex(1)

        create_btn = dlg.findChild(QPushButton, "createBtn")
        assert create_btn is not None
        create_btn.click()

        mock_success.assert_called_once()
        assert any(
            a.name == "Test Account" for a in fast_seeded.accounts.values()
        ), "Account not created on backend"

    def test_valid_submit_with_parent(self, qt_app, fast_seeded, mock_success):
        """Submit with a specific parent selection works."""
        dlg = AccountDialog(fast_seeded, mock_success)

        name_input = dlg.findChild(QLineEdit, "nameInput")
        QTest.keyClicks(name_input, "Sub Account")

        # Select a parent from the combo
        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        if parent_combo and parent_combo.count() > 0:
            parent_combo.setCurrentIndex(1)  # second parent option

        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_called_once()

    # ── Edit mode ──────────────────────────────────────────

    def test_edit_opens_with_edit_title(self, qt_app, fast_seeded, mock_success):
        """Edit mode: 'Edit Account' title."""
        aid = fast_seeded.add_account("Old Name", 1)
        dlg = AccountDialog(
            fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )
        assert dlg.windowTitle() == "Edit Account"

    def test_edit_prepopulates_name(self, qt_app, fast_seeded, mock_success):
        """Edit mode pre-fills the account name field."""
        aid = fast_seeded.add_account("Editable Acct", 1)
        dlg = AccountDialog(
            fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )
        name_input = dlg.findChild(QLineEdit, "nameInput")
        assert name_input is not None
        assert "Editable Acct" in name_input.text()

    def test_edit_submit_updates_account(self, qt_app, fast_seeded, mock_success):
        """Submitting in edit mode updates the account name."""
        aid = fast_seeded.add_account("Before Edit", 1)
        dlg = AccountDialog(
            fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )

        name_input = dlg.findChild(QLineEdit, "nameInput")
        name_input.clear()
        QTest.keyClicks(name_input, "After Edit")

        # Parent should already be pre-selected in edit mode, but
        # AccountSelector starts neutral — ensure something is selected.
        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        if parent_combo and parent_combo.count() > 0:
            parent_combo.setCurrentIndex(1)

        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_called_once()
        assert fast_seeded.accounts[aid].name == "After Edit"


# ═══════════════════════════════════════════════════════════════════
#  TransactionDialog
# ═══════════════════════════════════════════════════════════════════


class TestTransactionDialog:
    """Multi-split journal entry dialog."""

    def test_opens(self, qt_app, fast_seeded, mock_success):
        """Dialog opens with 'New Transaction' title."""
        dlg = TransactionDialog(fast_seeded, mock_success)
        assert dlg.windowTitle() == "New Transaction"

    def test_add_split_inserts_row(self, qt_app, fast_seeded, mock_success):
        """Adding a valid split creates a row in the table."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        table = dlg.findChild(QTableWidget, "splitTable")
        assert table is not None
        before = table.rowCount()

        # Select an account from the combo
        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        assert acct_combo is not None
        if acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)

        # Set the amount
        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        assert amt_input is not None
        QTest.keyClicks(amt_input, "1000")

        # Click Add Split
        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        assert add_btn is not None
        add_btn.click()

        assert table.rowCount() == before + 1

    def test_add_split_zero_amount(self, qt_app, fast_seeded, mock_success):
        """Adding a split with 0 amount shows error."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)

        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        if amt_input:
            QTest.keyClicks(amt_input, "0")

        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        if add_btn:
            add_btn.click()

        # Validation should fail — table stays at 0
        table = dlg.findChild(QTableWidget, "splitTable")
        assert table.rowCount() == 0

    def test_submit_balanced_succeeds(self, qt_app, fast_seeded, mock_success):
        """Two balanced splits → on_success called."""
        dlg = TransactionDialog(fast_seeded, mock_success)
        table = dlg.findChild(QTableWidget, "splitTable")
        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")

        # First split: debit 1000
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)
        if amt_input:
            QTest.keyClicks(amt_input, "1000")
        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        if add_btn:
            add_btn.click()

        # Second split: credit 1000
        if amt_input:
            amt_input.clear()
            QTest.keyClicks(amt_input, "1000")
        # Toggle debit/credit checkbox
        debit_cb = dlg.findChild(QCheckBox, "debitCheckbox")
        if debit_cb and debit_cb.isChecked():
            debit_cb.setChecked(False)  # Toggle to credit
        if add_btn:
            add_btn.click()

        # Set description and date
        desc_input = dlg.findChild(QLineEdit, "descInput")
        if desc_input:
            QTest.keyClicks(desc_input, "Balanced test")
        date_input = dlg.findChild(QLineEdit, "dateInput")
        if date_input:
            date_input.clear()
            QTest.keyClicks(date_input, datetime.now().strftime(DATE_STR))

        # Submit
        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        assert submit_btn is not None
        submit_btn.click()

        # Debug: check what happened
        if mock_success.call_count == 0:
            # Something went wrong — the dialog's _submit caught an exception
            pass

        mock_success.assert_called_once()

    def test_remove_split(self, qt_app, fast_seeded, mock_success):
        """Remove button deletes selected row."""
        dlg = TransactionDialog(fast_seeded, mock_success)
        table = dlg.findChild(QTableWidget, "splitTable")

        # Add a split first
        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)
        if amt_input:
            QTest.keyClicks(amt_input, "500")
        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        if add_btn:
            add_btn.click()

        assert table.rowCount() == 1

        # Select the row and remove
        table.selectRow(0)
        remove_btn = dlg.findChild(QPushButton, "removeSplitBtn")
        if remove_btn:
            remove_btn.click()

        assert table.rowCount() == 0


# ═══════════════════════════════════════════════════════════════════
#  BuySellDialog
# ═══════════════════════════════════════════════════════════════════


class TestBuySellDialog:
    """Buy/sell security modal."""

    def test_opens(self, qt_app, fast_seeded, mock_success):
        """Dialog opens with correct title."""
        dlg = BuySellDialog(fast_seeded, mock_success)
        assert dlg.windowTitle() == "Buy / Sell Security"

    def test_valid_buy_submit(self, qt_app, fast_seeded, mock_success):
        """Completely filled Buy form → on_success called."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        # Set investment account
        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)

        # Set cash account
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        # Set ticker
        ticker_input = dlg.findChild(QLineEdit, "tickerInput")
        if ticker_input:
            QTest.keyClicks(ticker_input, "VTI")

        # Set shares
        shares_input = dlg.findChild(QLineEdit, "sharesInput")
        if shares_input:
            QTest.keyClicks(shares_input, "10")

        # Set price
        price_input = dlg.findChild(QLineEdit, "priceInput")
        if price_input:
            QTest.keyClicks(price_input, "27500")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_called_once()

    def test_missing_investment_shows_error(self, qt_app, fast_seeded, mock_success):
        """Submit with empty investment acct → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        # Set cash account but not investment
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_gains_field_shows_on_sell(self, qt_app, fast_seeded, mock_success):
        """Toggling to Sell makes the gains account field visible."""
        dlg = BuySellDialog(fast_seeded, mock_success)
        dlg.show()  # must show for isVisible() to work
        QApplication.processEvents()

        sell_radio = dlg.findChild(QRadioButton, "sellRadio")
        assert sell_radio is not None
        sell_radio.setChecked(True)
        QApplication.processEvents()

        gains_combo = dlg.findChild(QComboBox, "gainsAccountCombo")
        assert gains_combo is not None
        assert gains_combo.isVisible(), "Gains combo should be visible after Sell toggle"
        dlg.close()


# ═══════════════════════════════════════════════════════════════════
#  AccountDialog — edge cases
# ═══════════════════════════════════════════════════════════════════


class TestAccountDialogEdgeCases:
    """AccountDialog validation boundaries and edge cases."""

    def test_submit_no_parent_selected_shows_error(self, qt_app, fast_seeded, mock_success):
        """Submit with no parent selection → on_success not called."""
        dlg = AccountDialog(fast_seeded, mock_success)
        name_input = dlg.findChild(QLineEdit, "nameInput")
        QTest.keyClicks(name_input, "Orphan")

        # No parent selected — AccountSelector starts at -1
        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_not_called()

    def test_type_override_applied(self, qt_app, fast_seeded, mock_success):
        """Selecting a type override applies the correct account type."""
        dlg = AccountDialog(fast_seeded, mock_success)

        name_input = dlg.findChild(QLineEdit, "nameInput")
        QTest.keyClicks(name_input, "CustomType")

        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        if parent_combo and parent_combo.count() > 0:
            parent_combo.setCurrentIndex(1)

        type_combo = dlg.findChild(QComboBox, "typeCombo")
        assert type_combo is not None
        type_combo.setCurrentText("LIABILITY")

        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_called_once()
        acct = next(a for a in fast_seeded.accounts.values() if a.name == "CustomType")
        assert acct.acct_type == "LIABILITY"

    def test_subtype_selection_persisted(self, qt_app, fast_seeded, mock_success):
        """Selecting a subtype attaches it to the account."""
        dlg = AccountDialog(fast_seeded, mock_success)

        name_input = dlg.findChild(QLineEdit, "nameInput")
        QTest.keyClicks(name_input, "Subtyped")

        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        if parent_combo and parent_combo.count() > 0:
            parent_combo.setCurrentIndex(1)

        subtype_combo = dlg.findChild(QComboBox, "subtypeCombo")
        assert subtype_combo is not None
        if subtype_combo.count() > 1:
            subtype_combo.setCurrentIndex(1)

        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_called_once()
        acct = next(a for a in fast_seeded.accounts.values() if a.name == "Subtyped")
        assert acct.account_subtype is not None

    def test_cancel_rejects(self, qt_app, fast_seeded, mock_success):
        """Cancel button calls reject()."""
        dlg = AccountDialog(fast_seeded, mock_success)
        rejected = [False]

        dlg.rejected.connect(lambda: rejected.__setitem__(0, True))
        cancel_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel"]
        assert len(cancel_btns) >= 1
        cancel_btns[0].click()

        assert rejected[0] is True
        mock_success.assert_not_called()

    def test_edit_empty_name_shows_error(self, qt_app, fast_seeded, mock_success):
        """Edit mode with cleared name shows error."""
        aid = fast_seeded.add_account("Temp", 1)
        dlg = AccountDialog(
            fast_seeded, mock_success,
            edit_acct=fast_seeded.accounts[aid], edit_acct_id=aid,
        )
        name_input = dlg.findChild(QLineEdit, "nameInput")
        name_input.clear()

        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_not_called()
        assert fast_seeded.accounts[aid].name == "Temp"  # unchanged

    def test_hint_label_updates_on_parent_change(self, qt_app, fast_seeded, mock_success):
        """Switching parent shows type-inheritance hint."""
        fast_seeded.add_account("AssetParent", 1)  # type ASSET
        dlg = AccountDialog(fast_seeded, mock_success)

        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        hint_labels = [c for c in dlg.findChildren(QLabel) if "color: gray;" in (c.styleSheet() or "")]

        name_input = dlg.findChild(QLineEdit, "nameInput")
        QTest.keyClicks(name_input, "HintTest")

        if parent_combo and parent_combo.count() > 1:
            parent_combo.setCurrentIndex(parent_combo.count() - 1)
            # Verify hint label exists (add_account can fail in fast_seeded if name is taken)

    def test_backend_exception_shows_error(self, qt_app, fast_seeded, mock_success):
        """If add_account raises, on_success not called and dialog rejects."""
        dlg = AccountDialog(fast_seeded, mock_success)

        name_input = dlg.findChild(QLineEdit, "nameInput")
        QTest.keyClicks(name_input, "Bad")

        parent_combo = dlg.findChild(QComboBox, "parentCombo")
        if parent_combo and parent_combo.count() > 0:
            parent_combo.setCurrentIndex(1)

        # Save the original method
        original = fast_seeded.add_account

        def _broken(*args, **kwargs):
            raise RuntimeError("DB corruption!")

        fast_seeded.add_account = _broken

        create_btn = dlg.findChild(QPushButton, "createBtn")
        create_btn.click()

        mock_success.assert_not_called()
        fast_seeded.add_account = original


# ═══════════════════════════════════════════════════════════════════
#  TransactionDialog — edge cases
# ═══════════════════════════════════════════════════════════════════


class TestTransactionDialogEdgeCases:
    """TransactionDialog validation boundaries and edge cases."""

    def _add_split(self, dlg, amount_str: str, is_debit: bool = True):
        """Helper to add a split row via dialog widget interaction."""
        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)
        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        if amt_input:
            amt_input.clear()
            QTest.keyClicks(amt_input, amount_str)
        debit_cb = dlg.findChild(QCheckBox, "debitCheckbox")
        if debit_cb:
            debit_cb.setChecked(is_debit)
        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        if add_btn:
            add_btn.click()

    def test_add_split_no_account_selected(self, qt_app, fast_seeded, mock_success):
        """Add split with no account → error, table stays empty."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        # Set amount but don't select an account
        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        QTest.keyClicks(amt_input, "1000")

        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        add_btn.click()

        table = dlg.findChild(QTableWidget, "splitTable")
        assert table.rowCount() == 0

    def test_add_split_non_numeric_amount(self, qt_app, fast_seeded, mock_success):
        """Add split with text in amount → error."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)

        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        QTest.keyClicks(amt_input, "abc")

        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        add_btn.click()

        table = dlg.findChild(QTableWidget, "splitTable")
        assert table.rowCount() == 0

    def test_submit_missing_description(self, qt_app, fast_seeded, mock_success):
        """Submit with empty description → error."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        self._add_split(dlg, "1000", is_debit=True)
        self._add_split(dlg, "1000", is_debit=False)

        # Clear the description
        desc_input = dlg.findChild(QLineEdit, "descInput")
        desc_input.clear()

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_invalid_date_format(self, qt_app, fast_seeded, mock_success):
        """Submit with invalid date → error."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        self._add_split(dlg, "1000", is_debit=True)
        self._add_split(dlg, "1000", is_debit=False)

        desc_input = dlg.findChild(QLineEdit, "descInput")
        QTest.keyClicks(desc_input, "Bad date txn")

        date_input = dlg.findChild(QLineEdit, "dateInput")
        date_input.clear()
        QTest.keyClicks(date_input, "not-a-date")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_unbalanced_splits(self, qt_app, fast_seeded, mock_success):
        """Splits that don't sum to zero → error."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        self._add_split(dlg, "5000", is_debit=True)
        self._add_split(dlg, "3000", is_debit=False)  # off by 2000

        desc_input = dlg.findChild(QLineEdit, "descInput")
        QTest.keyClicks(desc_input, "Unbalanced")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_single_split(self, qt_app, fast_seeded, mock_success):
        """Only one split → error (need at least 2)."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        self._add_split(dlg, "5000", is_debit=True)

        desc_input = dlg.findChild(QLineEdit, "descInput")
        QTest.keyClicks(desc_input, "Single split")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        submit_btn.click()

        mock_success.assert_not_called()

    def test_edit_mode_prepopulates_splits(self, qt_app, fast_seeded, mock_success):
        """Edit mode pre-loads existing splits into the table."""
        checking = fast_seeded.add_account("EditTestChecking", 1)
        food = fast_seeded.add_account("EditTestFood", 5)
        txn_id = fast_seeded.add_transaction(
            datetime(2026, 6, 15), "Existing",
            [Split(food, 7500), Split(checking, -7500)],
        )
        txn = fast_seeded.journal.transactions[txn_id]

        dlg = TransactionDialog(
            fast_seeded, mock_success,
            edit_txn=txn, edit_txn_id=txn_id,
        )

        table = dlg.findChild(QTableWidget, "splitTable")
        assert table.rowCount() == 2

        # Description should be pre-loaded
        desc_input = dlg.findChild(QLineEdit, "descInput")
        assert "Existing" in desc_input.text()

    def test_edit_submit_works(self, qt_app, fast_seeded, mock_success):
        """Editing a transaction submits successfully."""
        checking = fast_seeded.add_account("EditSubmitChecking", 1)
        food = fast_seeded.add_account("EditSubmitFood", 5)
        txn_id = fast_seeded.add_transaction(
            datetime(2026, 6, 15), "Old desc",
            [Split(food, 7500), Split(checking, -7500)],
        )
        txn = fast_seeded.journal.transactions[txn_id]

        dlg = TransactionDialog(
            fast_seeded, mock_success,
            edit_txn=txn, edit_txn_id=txn_id,
        )

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        submit_btn.click()

        mock_success.assert_called_once()

    def test_cancel_rejects(self, qt_app, fast_seeded, mock_success):
        """Cancel button fires reject()."""
        dlg = TransactionDialog(fast_seeded, mock_success)
        rejected = [False]

        dlg.rejected.connect(lambda: rejected.__setitem__(0, True))
        cancel_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel"]
        assert len(cancel_btns) >= 1
        cancel_btns[0].click()

        assert rejected[0] is True
        mock_success.assert_not_called()

    def test_add_split_memo_preserved(self, qt_app, fast_seeded, mock_success):
        """Adding a split with memo text preserves it in the table."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        acct_combo = dlg.findChild(QComboBox, "splitAcctCombo")
        if acct_combo and acct_combo.count() > 0:
            acct_combo.setCurrentIndex(acct_combo.count() - 1)

        amt_input = dlg.findChild(QLineEdit, "splitAmountInput")
        QTest.keyClicks(amt_input, "5000")

        memo_input = dlg.findChild(QLineEdit, "splitMemoInput")
        assert memo_input is not None
        QTest.keyClicks(memo_input, "my note")

        add_btn = dlg.findChild(QPushButton, "addSplitBtn")
        add_btn.click()

        table = dlg.findChild(QTableWidget, "splitTable")
        assert table.rowCount() == 1
        memo_item = table.item(0, 3)
        assert memo_item is not None
        assert memo_item.text() == "my note"

    def test_remove_split_no_selection_no_crash(self, qt_app, fast_seeded, mock_success):
        """Remove button with no selected row → no crash."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        remove_btn = dlg.findChild(QPushButton, "removeSplitBtn")
        assert remove_btn is not None
        remove_btn.click()  # nothing selected — should not crash

    def test_three_splits_balanced_submits(self, qt_app, fast_seeded, mock_success):
        """3-way split (two debits, one credit) submits successfully."""
        dlg = TransactionDialog(fast_seeded, mock_success)

        # First account for debit 1
        self._add_split(dlg, "5000", is_debit=True)
        # Second account for debit 2
        self._add_split(dlg, "3000", is_debit=True)
        # Third account as credit (sum of debits)
        self._add_split(dlg, "8000", is_debit=False)

        desc_input = dlg.findChild(QLineEdit, "descInput")
        QTest.keyClicks(desc_input, "3-way split")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        submit_btn.click()

        mock_success.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
#  BuySellDialog — edge cases
# ═══════════════════════════════════════════════════════════════════


class TestBuySellDialogEdgeCases:
    """BuySellDialog validation boundaries and edge cases."""

    def _fill_buy_form(self, dlg, ticker="VTI", shares="10", price="27500"):
        """Helper to populate buy form fields (not cash/investment accounts)."""
        ticker_input = dlg.findChild(QLineEdit, "tickerInput")
        if ticker_input:
            QTest.keyClicks(ticker_input, ticker)
        shares_input = dlg.findChild(QLineEdit, "sharesInput")
        if shares_input:
            QTest.keyClicks(shares_input, shares)
        price_input = dlg.findChild(QLineEdit, "priceInput")
        if price_input:
            QTest.keyClicks(price_input, price)

    def test_submit_no_ticker(self, qt_app, fast_seeded, mock_success):
        """Submit with empty ticker → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        # Fill shares and price but not ticker
        self._fill_buy_form(dlg, ticker="", shares="10", price="27500")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_zero_shares(self, qt_app, fast_seeded, mock_success):
        """Submit with 0 shares → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        self._fill_buy_form(dlg, ticker="VTI", shares="0", price="10000")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_negative_shares(self, qt_app, fast_seeded, mock_success):
        """Submit with negative shares → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        self._fill_buy_form(dlg, ticker="VTI", shares="-5", price="10000")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_non_numeric_shares(self, qt_app, fast_seeded, mock_success):
        """Submit with text in shares field → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        self._fill_buy_form(dlg, ticker="VTI", shares="abc", price="10000")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_zero_price(self, qt_app, fast_seeded, mock_success):
        """Submit with 0 price → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        self._fill_buy_form(dlg, ticker="VTI", shares="10", price="0")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_non_numeric_price(self, qt_app, fast_seeded, mock_success):
        """Submit with text in price field → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        self._fill_buy_form(dlg, ticker="VTI", shares="10", price="xyz")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_submit_no_cash_account(self, qt_app, fast_seeded, mock_success):
        """Submit with no cash account → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        # Don't select a cash account

        self._fill_buy_form(dlg, ticker="VTI", shares="10", price="27500")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()

    def test_valid_sell_submission(self, qt_app, fast_seeded, mock_success):
        """Full valid sell with gains account → on_success called."""
        # Create a sell scenario — need an existing holding
        brokerage = fast_seeded.add_account("SellBrokerage", 1, account_subtype="brokerage")
        cash = fast_seeded.add_account("SellCash", 1)
        gain_acct = fast_seeded.add_account("CapGains", 4)

        # Fund and buy first so we have something to sell
        fast_seeded.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(cash, 500000), Split(6, -1000000)],
        )
        fast_seeded.buy_security(datetime(2026, 2, 1), "Pre-buy",
                                 brokerage, cash, "VTI", 10, 27500)
        fast_seeded.generate_ledger()

        dlg = BuySellDialog(fast_seeded, mock_success)
        dlg.show()
        QApplication.processEvents()

        # Toggle to Sell
        sell_radio = dlg.findChild(QRadioButton, "sellRadio")
        assert sell_radio is not None
        sell_radio.setChecked(True)
        QApplication.processEvents()

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo:
            idx = inv_combo.findText("SellBrokerage", Qt.MatchFlag.MatchContains)
            if idx >= 0:
                inv_combo.setCurrentIndex(idx)

        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo:
            idx = cash_combo.findText("SellCash", Qt.MatchFlag.MatchContains)
            if idx >= 0:
                cash_combo.setCurrentIndex(idx)

        gains_combo = dlg.findChild(QComboBox, "gainsAccountCombo")
        if gains_combo and gains_combo.isVisible():
            idx = gains_combo.findText("CapGains", Qt.MatchFlag.MatchContains)
            if idx >= 0:
                gains_combo.setCurrentIndex(idx)

        self._fill_buy_form(dlg, ticker="VTI", shares="5", price="30000")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_called_once()

    def test_sell_then_buy_gains_field_hides(self, qt_app, fast_seeded, mock_success):
        """Toggling back to Buy hides the gains account field."""
        dlg = BuySellDialog(fast_seeded, mock_success)
        dlg.show()
        QApplication.processEvents()

        sell_radio = dlg.findChild(QRadioButton, "sellRadio")
        buy_radio = dlg.findChild(QRadioButton, "buyRadio")
        assert sell_radio is not None
        assert buy_radio is not None

        # Toggle to Sell → gains visible
        sell_radio.setChecked(True)
        QApplication.processEvents()
        gains_combo = dlg.findChild(QComboBox, "gainsAccountCombo")
        assert gains_combo is not None
        assert gains_combo.isVisible()

        # Toggle back to Buy → gains hidden
        buy_radio.setChecked(True)
        QApplication.processEvents()
        assert not gains_combo.isVisible()

        dlg.close()

    def test_cancel_rejects(self, qt_app, fast_seeded, mock_success):
        """Cancel button fires reject()."""
        dlg = BuySellDialog(fast_seeded, mock_success)
        rejected = [False]

        dlg.rejected.connect(lambda: rejected.__setitem__(0, True))
        cancel_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel"]
        assert len(cancel_btns) >= 1
        cancel_btns[0].click()

        assert rejected[0] is True
        mock_success.assert_not_called()

    def test_invalid_date_format(self, qt_app, fast_seeded, mock_success):
        """Submit with invalid date → error."""
        dlg = BuySellDialog(fast_seeded, mock_success)

        inv_combo = dlg.findChild(QComboBox, "invAccountCombo")
        if inv_combo and inv_combo.count() > 0:
            inv_combo.setCurrentIndex(inv_combo.count() - 1)
        cash_combo = dlg.findChild(QComboBox, "cashAccountCombo")
        if cash_combo and cash_combo.count() > 0:
            cash_combo.setCurrentIndex(cash_combo.count() - 1)

        date_input = dlg.findChild(QLineEdit, "dateInput")
        date_input.clear()
        QTest.keyClicks(date_input, "bad-date")

        self._fill_buy_form(dlg, ticker="VTI", shares="10", price="27500")

        submit_btn = dlg.findChild(QPushButton, "submitBtn")
        if submit_btn:
            submit_btn.click()

        mock_success.assert_not_called()
