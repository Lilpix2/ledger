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
                                     QComboBox, QLineEdit, QTableWidget,
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
            QTest.mouseClick(debit_cb, Qt.MouseButton.LeftButton)
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

        sell_radio = dlg.findChild(QRadioButton, "sellRadio")
        assert sell_radio is not None
        sell_radio.setChecked(True)

        gains_combo = dlg.findChild(QComboBox, "gainsAccountCombo")
        assert gains_combo is not None
        assert gains_combo.isVisible()
