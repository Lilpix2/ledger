"""Component tests: PySide6 — ``DeleteAccountDialog``.

Tests
-----
- Shows child reassignment section when children exist
- Shows transaction reassignment section when txns exist
- Reassigns children and/or transactions before deletion
- Cascade checkboxes work
- Cancel does nothing
- Root account blocked

Boundary
--------
- Backend mocked via ``fast_manager`` / ``fast_seeded`` (MockDB)
- Dialogs created without ``exec()`` (no modal blocking)
- ``on_success`` is a ``MagicMock``
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, ANY

import pytest

try:
    from PySide6.QtWidgets import (QApplication, QDialog, QPushButton,
                                     QComboBox, QLineEdit, QCheckBox,
                                     QLabel, QGroupBox)
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False

from ledger.models.data_class import Split

from ledger.gui_pyside.dialogs import DeleteAccountDialog



class TestDeleteAccountDialog:
    """Delete account dialog with child/txn reassignment options."""

    # ── No complications — simple delete ────────────────────

    def test_simple_delete_no_children_no_txns(
        self, qt_app, fast_seeded, mock_success,
    ):
        """Account with no children and no transactions — delete succeeds."""
        

        acct_id = fast_seeded.add_account("Simple", 1)
        dlg = DeleteAccountDialog(fast_seeded, acct_id, mock_success)

        # Simple path: dialog is accepted (not shown), on_success called
        mock_success.assert_called_once()
        assert acct_id not in fast_seeded.accounts

    # ── Root account blocked ──────────────────────────────

    def test_delete_root_blocked(self, qt_app, fast_seeded, mock_success):
        """Root account deletion shows error and rejects dialog."""
        

        dlg = DeleteAccountDialog(fast_seeded, 0, mock_success)
        mock_success.assert_not_called()

    # ── With children ──────────────────────────────────────

    def test_children_section_shown(self, qt_app, fast_seeded, mock_success):
        """When account has children, a group box for children appears."""
        

        parent = fast_seeded.add_account("Parent", 1)
        fast_seeded.add_account("Child", parent)

        dlg = DeleteAccountDialog(fast_seeded, parent, mock_success)
        child_group = dlg.findChild(QGroupBox, "childGroup")
        assert child_group is not None
        assert child_group.isVisible()

    def test_children_reassigned_via_dropdown(
        self, qt_app, fast_seeded, mock_success,
    ):
        """Selecting a target for children → children reparented."""
        

        parent = fast_seeded.add_account("Parent", 1)
        child = fast_seeded.add_account("Child", parent)
        target = fast_seeded.add_account("TargetParent", 1)

        dlg = DeleteAccountDialog(fast_seeded, parent, mock_success)

        child_combo = dlg.findChild(QComboBox, "childTargetCombo")
        assert child_combo is not None
        # Find the target in the combo
        target_idx = child_combo.findText("TargetParent", Qt.MatchFlag.MatchContains)
        if target_idx >= 0:
            child_combo.setCurrentIndex(target_idx)

        delete_btn = dlg.findChild(QPushButton, "deleteBtn")
        if delete_btn:
            delete_btn.click()

        mock_success.assert_called_once()
        assert parent not in fast_seeded.accounts
        assert fast_seeded.accounts[child].parent == target

    # ── With transactions ──────────────────────────────────

    def test_transactions_section_shown(self, qt_app, fast_seeded, mock_success):
        """When account has transactions, a group box for txns appears."""
        

        source = fast_seeded.add_account("Source", 1)
        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(source, 100000), Split(6, -100000)],
        )
        fast_seeded.generate_ledger()

        dlg = DeleteAccountDialog(fast_seeded, source, mock_success)
        txn_group = dlg.findChild(QGroupBox, "transactionGroup")
        assert txn_group is not None
        assert txn_group.isVisible()

    def test_transactions_reassigned_via_dropdown(
        self, qt_app, fast_seeded, mock_success,
    ):
        """Selecting a target for transactions → splits migrated."""
        

        source = fast_seeded.add_account("Source", 1)
        target = fast_seeded.add_account("Target", 1)
        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(source, 200000), Split(6, -200000)],
        )
        fast_seeded.generate_ledger()

        dlg = DeleteAccountDialog(fast_seeded, source, mock_success)

        txn_combo = dlg.findChild(QComboBox, "txnTargetCombo")
        if txn_combo:
            target_idx = txn_combo.findText("Target", Qt.MatchFlag.MatchContains)
            if target_idx >= 0:
                txn_combo.setCurrentIndex(target_idx)

        delete_btn = dlg.findChild(QPushButton, "deleteBtn")
        if delete_btn:
            delete_btn.click()

        mock_success.assert_called_once()
        assert source not in fast_seeded.accounts
        assert fast_seeded.get_display_balance(target) == 200000

    # ── Both children and transactions ─────────────────────

    def test_both_reassigned(self, qt_app, fast_seeded, mock_success):
        """Both children and transactions reassigned before delete."""
        

        parent = fast_seeded.add_account("Parent", 1)
        child = fast_seeded.add_account("Child", parent)
        txn_target = fast_seeded.add_account("TxnTarget", 1)
        child_target = fast_seeded.add_account("ChildTarget", 1)

        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(parent, 150000), Split(6, -150000)],
        )
        fast_seeded.generate_ledger()

        dlg = DeleteAccountDialog(fast_seeded, parent, mock_success)

        # Set child target
        child_combo = dlg.findChild(QComboBox, "childTargetCombo")
        if child_combo:
            idx = child_combo.findText("ChildTarget", Qt.MatchFlag.MatchContains)
            if idx >= 0:
                child_combo.setCurrentIndex(idx)

        # Set txn target
        txn_combo = dlg.findChild(QComboBox, "txnTargetCombo")
        if txn_combo:
            idx = txn_combo.findText("TxnTarget", Qt.MatchFlag.MatchContains)
            if idx >= 0:
                txn_combo.setCurrentIndex(idx)

        delete_btn = dlg.findChild(QPushButton, "deleteBtn")
        if delete_btn:
            delete_btn.click()

        mock_success.assert_called_once()
        assert parent not in fast_seeded.accounts
        assert fast_seeded.accounts[child].parent == child_target
        assert fast_seeded.get_display_balance(txn_target) == 150000

    # ── Cascade checkbox ───────────────────────────────────

    def test_cascade_children(self, qt_app, fast_seeded, mock_success):
        """Checking 'Delete children too' cascades children."""
        

        parent = fast_seeded.add_account("Parent", 1)
        child = fast_seeded.add_account("Child", parent)
        txn_target = fast_seeded.add_account("TxnTarget", 1)

        fast_seeded.add_transaction(
            datetime(2026, 6, 1), "Fund",
            [Split(parent, 50000), Split(6, -50000)],
        )
        fast_seeded.generate_ledger()

        dlg = DeleteAccountDialog(fast_seeded, parent, mock_success)

        # Check the cascade checkbox for children
        child_cascade = dlg.findChild(QCheckBox, "childCascadeCheck")
        if child_cascade:
            child_cascade.setChecked(True)

        # Set txn target (don't cascade txns)
        txn_combo = dlg.findChild(QComboBox, "txnTargetCombo")
        if txn_combo:
            idx = txn_combo.findText("TxnTarget", Qt.MatchFlag.MatchContains)
            if idx >= 0:
                txn_combo.setCurrentIndex(idx)

        delete_btn = dlg.findChild(QPushButton, "deleteBtn")
        if delete_btn:
            delete_btn.click()

        mock_success.assert_called_once()
        assert parent not in fast_seeded.accounts
        assert child not in fast_seeded.accounts  # cascaded
        assert fast_seeded.get_display_balance(txn_target) == 50000  # migrated

    # ── Cancel ─────────────────────────────────────────────

    def test_cancel_does_nothing(self, qt_app, fast_seeded, mock_success):
        """Cancel button rejects without deleting."""
        

        acct = fast_seeded.add_account("CancelTest", 1)
        before = len(fast_seeded.accounts)

        dlg = DeleteAccountDialog(fast_seeded, acct, mock_success, show_dialog=False)
        cancel_btn = dlg.findChild(QPushButton, "cancelBtn")
        if cancel_btn:
            cancel_btn.click()

        mock_success.assert_not_called()
        assert len(fast_seeded.accounts) == before
