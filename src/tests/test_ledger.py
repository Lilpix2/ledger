"""Unit tests: journal transactions, ledger integrity, trial balance.

All tests use ``fast_manager`` or ``fast_seeded`` (MockDB, zero disk I/O).
AAA pattern enforced throughout.
"""

import pytest
from datetime import datetime

from ledger.models.data_class import Split, JournalTransaction, Holding, Price


# ═══════════════════════════════════════════════════════════════════
# JournalTransactions
# ═══════════════════════════════════════════════════════════════════

class TestJournalTransactions:
    """Creating and validating compound journal entries."""

    # ── add_transaction ───────────────────────────────────────────

    def test_addTransaction_simple_returnsId(self, fast_manager):
        """Arrange: two accounts. Act: add a balanced 2-split txn.
        Assert: returns non-negative id, stored in journal."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)

        # Act
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 15), "Weekly shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )

        # Assert
        assert txn_id >= 0
        assert txn_id in fast_manager.journal.transactions

    def test_addTransaction_compound3Splits_returnsId(self, fast_manager):
        """Arrange: three accounts. Act: add a 3-split balanced txn.
        Assert: returns non-negative id."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        savings = fast_manager.add_account("Savings", 1)
        salary = fast_manager.add_account("Salary", 4)

        # Act
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 15), "Payday split",
            [Split(salary, -200000), Split(checking, 150000),
             Split(savings, 50000)],
        )

        # Assert
        assert txn_id >= 0

    def test_addTransaction_unbalanced_raises(self, fast_manager):
        """Arrange: two accounts. Act: unbalanced splits. Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)

        # Act & Assert
        with pytest.raises(ValueError, match="Unbalanced"):
            fast_manager.add_transaction(
                datetime(2026, 1, 15), "Bad",
                [Split(groceries, 5000), Split(checking, -4000)],
            )

    def test_addTransaction_emptySplits_raises(self, fast_manager):
        """Arrange: no accounts needed. Act: empty splits list. Assert: ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="at least one split"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Empty", [])

    def test_addTransaction_zeroAmountSplit_raises(self, fast_manager):
        """Arrange: accounts. Act: split with amount=0. Assert: ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)

        # Act & Assert
        with pytest.raises(ValueError, match="non-zero"):
            fast_manager.add_transaction(
                datetime(2026, 1, 1), "Zero",
                [Split(groceries, 0), Split(checking, 100), Split(checking, -100)],
            )

    def test_addTransaction_nonexistentAccount_raises(self, fast_manager):
        """Arrange: no accounts (99999 doesn't exist). Act: add split with bad ID.
        Assert: ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="account"):
            fast_manager.add_transaction(
                datetime(2026, 1, 1), "Bad",
                [Split(99999, 100), Split(2, -100)],
            )

    def test_addTransaction_negativeAmount_works(self, fast_manager):
        """Arrange: two accounts. Act: add txn with negative splits.
        Assert: id stored."""
        # Arrange
        a = fast_manager.add_account("A", 1)
        b = fast_manager.add_account("B", 5)
        # Negative debits are valid if balanced by positive credits

        # Act
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 1), "Negatives",
            [Split(a, -5000), Split(b, 5000)],
        )

        # Assert
        assert txn_id in fast_manager.journal.transactions

    def test_addTransaction_twoSplitsSameAccount_works(self, fast_manager):
        """Arrange: accounts. Act: two splits on same account (net zero).
        Assert: txn stored."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)

        # Act
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 1), "Double split same acct",
            [Split(groceries, 5000), Split(checking, -3000), Split(checking, -2000)],
        )

        # Assert
        assert txn_id in fast_manager.journal.transactions


# ═══════════════════════════════════════════════════════════════════
# LedgerIntegrity
# ═══════════════════════════════════════════════════════════════════

class TestLedgerIntegrity:
    """Ledger generation, trial balance, chronological ordering, close_temps."""

    def test_generateLedger_updatesBalances(self, fast_manager):
        """Arrange: accounts and txns. Act: generate_ledger. Assert: balances match."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)
        salary = fast_manager.add_account("Salary", 4)
        fast_manager.add_transaction(
            datetime(2026, 1, 15), "Payday",
            [Split(salary, -200000), Split(checking, 200000)],
        )
        fast_manager.add_transaction(
            datetime(2026, 1, 16), "Shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )

        # Act
        fast_manager.generate_ledger()

        # Assert
        assert fast_manager.accounts[checking].get_balance() == 195000
        assert fast_manager.accounts[groceries].get_balance() == 5000
        assert fast_manager.accounts[salary].get_balance() == -200000

    def test_trialBalance_sumZero(self, fast_manager):
        """Arrange: income + expense txns. Act: generate_ledger.
        Assert: sum of all account balances = 0."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        income = fast_manager.add_account("Income", 4)
        expense = fast_manager.add_account("Expense", 5)
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Txn",
            [Split(income, -1000), Split(checking, 1000)],
        )
        fast_manager.add_transaction(
            datetime(2026, 1, 2), "Txn",
            [Split(expense, 500), Split(checking, -500)],
        )

        # Act
        fast_manager.generate_ledger()

        # Assert
        total = sum(a.get_balance() for a in fast_manager.accounts.values())
        assert total == 0, f"Trial balance is {total}, expected 0"

    def test_chronologicalOrder_returnsSorted(self, fast_manager):
        """Arrange: txns out of order. Act: chronological(). Assert: sorted dates."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        salary = fast_manager.add_account("Salary", 4)
        expenses = fast_manager.add_account("Expenses", 5)

        fast_manager.add_transaction(
            datetime(2026, 3, 1), "March",
            [Split(expenses, 100), Split(checking, -100)],
        )
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "January",
            [Split(salary, -2000), Split(checking, 2000)],
        )
        fast_manager.add_transaction(
            datetime(2026, 2, 1), "February",
            [Split(salary, -500), Split(checking, 500)],
        )

        # Act
        ordered = fast_manager.journal.chronological()

        # Assert
        dates = [txn.date.strftime("%Y-%m-%d") for txn in ordered]
        assert dates == sorted(dates)

    def test_closeTemps_resetsIncomeExpenseToZero(self, fast_seeded):
        """Arrange: seeded manager with transactions. Act: close_temps then
        generate_ledger. Assert: income/expense accounts reset to 0."""
        # Arrange — fast_seeded has Wages (income) and Groceries (expense) with txns
        # The opening balances in fast_seeded use account 6 (retained earnings) for equity,
        # Wages is account 15, Groceries is account 16.
        ids_by_name = {
            acct.name: aid
            for aid, acct in fast_seeded.accounts.items()
            if aid and acct.name
        }

        # Act
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()

        # Assert — income and expense accounts should be zero after close
        for name in ("Wages", "Groceries"):
            aid = ids_by_name.get(name)
            if aid is not None:
                assert fast_seeded.accounts[aid].get_balance() == 0, (
                    f"{name} not reset after close_temps"
                )

    def test_closeTemps_multipleTxns_resetsAll(self, fast_seeded):
        """Arrange: seeded manager. Act: add extra txn, close_temps.
        Assert: all temps reset."""
        # Arrange
        ids_by_name = {
            acct.name: aid
            for aid, acct in fast_seeded.accounts.items()
            if aid and acct.name
        }
        wages = ids_by_name["Wages"]
        groceries = ids_by_name["Groceries"]
        checking = ids_by_name["HS Checking"]

        # Add another income and expense
        fast_seeded.add_transaction(
            datetime(2026, 6, 15), "Bonus",
            [Split(wages, -50000), Split(checking, 50000)],
        )
        fast_seeded.add_transaction(
            datetime(2026, 6, 16), "More groceries",
            [Split(groceries, 2000), Split(checking, -2000)],
        )
        fast_seeded.generate_ledger()

        # Act
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()

        # Assert
        assert fast_seeded.accounts[wages].get_balance() == 0
        assert fast_seeded.accounts[groceries].get_balance() == 0


# ═══════════════════════════════════════════════════════════════════
# DataClassModels
# ═══════════════════════════════════════════════════════════════════

class TestDataClassModels:
    """Data class behavior and serialization."""

    # ── Split ─────────────────────────────────────────────────────

    def test_split_defaultMemo_empty(self):
        """Arrange: Split with no memo. Assert: memo defaults to ''."""
        # Arrange & Act
        s = Split(account_id=1, amount=5000)

        # Assert
        assert s.memo == ""

    def test_split_customMemo_stored(self):
        """Arrange: Split with custom memo. Assert: memo preserved."""
        # Arrange & Act
        s = Split(account_id=1, amount=5000, memo="test")

        # Assert
        assert s.memo == "test"

    def test_split_emptyMemoString(self):
        """Arrange: Split with empty string memo. Assert: memo is empty."""
        # Arrange & Act
        s = Split(account_id=1, amount=5000, memo="")

        # Assert
        assert s.memo == ""

    def test_split_zeroAmount_accepted(self):
        """Arrange: Split with zero amount. Assert: fields set correctly.
        (Validation is done at transaction level, not Split level.)"""
        # Arrange & Act
        s = Split(account_id=1, amount=0)

        # Assert
        assert s.account_id == 1
        assert s.amount == 0

    def test_split_negativeAmount(self):
        """Arrange: Split with negative amount. Assert: stored as-is."""
        # Arrange & Act
        s = Split(account_id=1, amount=-5000)

        # Assert
        assert s.amount == -5000

    # ── JournalTransaction ───────────────────────────────────────

    def test_journalTransaction_total_sumOfDebits(self):
        """Arrange: txn with 3 splits (two debits, one credit).
        Assert: total() returns sum of all positive (debit) amounts."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Test",
            [Split(1, 5000), Split(2, -3000), Split(6, -2000)],
        )

        # Act & Assert
        assert txn.total() == 5000

    def test_journalTransaction_validate_balanced_returnsTrue(self):
        """Arrange: balanced txn. Assert: validate() is True."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Good",
            [Split(1, 100), Split(2, -100)],
        )

        # Act & Assert
        assert txn.validate() is True

    def test_journalTransaction_validate_unbalanced_returnsFalse(self):
        """Arrange: unbalanced txn (100 + -50 = 50 ≠ 0). Assert: False."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Bad",
            [Split(1, 100), Split(2, -50)],
        )

        # Act & Assert
        assert txn.validate() is False

    def test_journalTransaction_validate_singleSplit_returnsFalse(self):
        """Arrange: txn with only one split (can't balance). Assert: False."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Single",
            [Split(1, 100)],
        )

        # Act & Assert
        assert txn.validate() is False

    def test_journalTransaction_total_emptySplits_returnsZero(self):
        """Arrange: txn with no splits. Assert: total() == 0."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Empty", [],
        )

        # Act & Assert
        assert txn.total() == 0

    def test_journalTransaction_total_multipleDebits(self):
        """Arrange: txn with 2 debit splits and 1 credit.
        Assert: total() = sum of all debits."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Multiple",
            [Split(1, 5000), Split(2, 3000), Split(3, -8000)],
        )

        # Act & Assert
        assert txn.total() == 8000

    def test_journalTransaction_validate_emptySplits_returnsTrue(self):
        """Arrange: txn with empty splits. Assert: validate() is True
        (sum([]) == 0 checks out)."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Empty", [],
        )

        # Act & Assert
        assert txn.validate() is True

    def test_journalTransaction_dict_roundtrips(self):
        """Arrange: txn with splits. Act: __dict__(). Assert: keys present."""
        # Arrange
        txn = JournalTransaction(
            datetime(2026, 1, 1), "Test",
            [Split(1, 5000), Split(2, -5000)],
        )

        # Act
        d = txn.__dict__()

        # Assert
        assert d["description"] == "Test"
        assert len(d["splits"]) == 2

    # ── Holding ───────────────────────────────────────────────────

    def test_holdingDataclass_fieldsStored(self):
        """Arrange: Holding with all fields. Assert: all fields match."""
        # Arrange & Act
        h = Holding(account_id=1, ticker="VTI", shares=100.5, cost_basis_cents=2750000)

        # Assert
        assert h.account_id == 1
        assert h.ticker == "VTI"
        assert h.shares == 100.5
        assert h.cost_basis_cents == 2750000

    def test_holding_zeroShares(self):
        """Arrange: Holding with 0 shares. Assert: stored."""
        # Arrange & Act
        h = Holding(account_id=1, ticker="VTI", shares=0.0, cost_basis_cents=0)

        # Assert
        assert h.shares == 0.0

    def test_holding_negativeShares(self):
        """Arrange: Holding with negative shares. Assert: stored as-is (no validation)."""
        # Arrange & Act
        h = Holding(account_id=1, ticker="VTI", shares=-5.0, cost_basis_cents=1000)

        # Assert
        assert h.shares == -5.0

    # ── Price ─────────────────────────────────────────────────────

    def test_priceDataclass_fieldsStored(self):
        """Arrange: Price with all fields. Assert: all fields match."""
        # Arrange & Act
        p = Price(ticker="VTI", date="2026-05-13", price_cents=27500)

        # Assert
        assert p.ticker == "VTI"
        assert p.price_cents == 27500

    def test_price_zeroCents(self):
        """Arrange: Price with 0 price_cents. Assert: stored."""
        # Arrange & Act
        p = Price(ticker="AAPL", date="2026-01-01", price_cents=0)

        # Assert
        assert p.price_cents == 0

    def test_price_negativeCents(self):
        """Arrange: Price with negative cents. Assert: stored as-is."""
        # Arrange & Act
        p = Price(ticker="VTI", date="2026-01-01", price_cents=-100)

        # Assert
        assert p.price_cents == -100

    # ── LedgerEntry ───────────────────────────────────────────────

    def test_ledgerEntry_dict_debitEntry(self):
        """Arrange: LedgerEntry with debit. Act: __dict__(). Assert: debit field."""
        # Arrange
        from ledger.models.data_class import LedgerEntry
        entry = LedgerEntry(datetime(2026, 1, 1), "Test", 0, 5000, 5000)

        # Act
        d = entry.__dict__()

        # Assert
        assert d["debit"] == 5000
        assert d["credit"] == 0
        assert d["balance"] == 5000
        assert d["description"] == "Test"

    def test_ledgerEntry_dict_creditEntry(self):
        """Arrange: LedgerEntry with credit. Act: __dict__(). Assert: credit field."""
        # Arrange
        from ledger.models.data_class import LedgerEntry
        entry = LedgerEntry(datetime(2026, 1, 2), "Credit", 10000, 0, -10000)

        # Act
        d = entry.__dict__()

        # Assert
        assert d["credit"] == 10000
        assert d["debit"] == 0
        assert d["balance"] == -10000

    def test_ledgerEntry_dict_zeroFields(self):
        """Arrange: LedgerEntry with all zeros. Assert: roundtrip."""
        # Arrange
        from ledger.models.data_class import LedgerEntry
        entry = LedgerEntry(datetime(2026, 1, 1), "Zero", 0, 0, 0)

        # Act
        d = entry.__dict__()

        # Assert
        assert d["debit"] == 0
        assert d["credit"] == 0
        assert d["balance"] == 0
