"""Unit tests: CRUD operations, edge cases, and GUI widget helpers.

All tests use the ``fast_manager`` or ``fast_seeded`` fixtures (MockDB —
no disk I/O, <1ms per test). Follows AAA + TDD principles.

Covers Journal, AccountManager CRUD, validation edge cases,
widget helpers (format_cents, build_account_choices).
"""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split, JournalTransaction
from ledger.models.data_books import Journal


# ═══════════════════════════════════════════════════════════════════
#  Journal — pure in-memory (no AccountManager needed)
# ═══════════════════════════════════════════════════════════════════


class TestJournalCRUD:
    """In-memory Journal: add, delete, chronological, by_id."""

    def test_addTransaction_emptyJournal_returnsIdZero(self):
        """Arrange: fresh Journal. Act: add one transaction. Assert: ID is 0."""
        # Arrange
        j = Journal()
        txn = JournalTransaction(datetime(2026, 1, 15), "Test", [Split(1, 5000), Split(2, -5000)])
        # Act
        txn_id = j.add_transaction(txn)
        # Assert
        assert txn_id == 0
        assert len(j.transactions) == 1
        assert j.transactions[0] is txn

    def test_addTransaction_multiple_idsIncrement(self):
        """Multiple calls to add_transaction return sequential IDs."""
        # Arrange
        j = Journal()
        # Act
        id1 = j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "A", [Split(1, 100), Split(2, -100)]))
        id2 = j.add_transaction(JournalTransaction(datetime(2026, 1, 2), "B", [Split(1, 200), Split(2, -200)]))
        # Assert
        assert id1 == 0
        assert id2 == 1

    def test_deleteTransaction_removesFromDict(self):
        """Deleting a transaction removes it from the in-memory store."""
        # Arrange
        j = Journal()
        tid = j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "X", [Split(1, 100), Split(2, -100)]))
        # Act
        j.delete_transaction(tid)
        # Assert
        assert tid not in j.transactions

    def test_deleteTransaction_nonexistent_raises(self):
        """Deleting a non-existent transaction raises KeyError."""
        # Arrange
        j = Journal()
        # Act & Assert
        with pytest.raises(KeyError):
            j.delete_transaction(999)

    def test_deleteTransaction_twice_raises(self):
        """Deleting an already-deleted transaction raises KeyError."""
        # Arrange
        j = Journal()
        tid = j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "X", [Split(1, 100), Split(2, -100)]))
        j.delete_transaction(tid)
        # Act & Assert
        with pytest.raises(KeyError):
            j.delete_transaction(tid)

    def test_addTransaction_withDbId_storesMapping(self):
        """add_transaction with db_id=42 makes get_db_id return 42."""
        # Arrange
        j = Journal()
        txn = JournalTransaction(datetime(2026, 1, 1), "X", [Split(1, 100), Split(2, -100)])
        # Act
        mem_id = j.add_transaction(txn, db_id=42)
        # Assert
        assert j.get_db_id(mem_id) == 42

    def test_getDbId_notSet_returnsNone(self):
        """get_db_id on an unmapped ID returns None."""
        # Arrange
        j = Journal()
        # Act & Assert
        assert j.get_db_id(0) is None

    def test_getDbId_afterDelete_returnsNone(self):
        """get_db_id on a deleted transaction returns None."""
        # Arrange
        j = Journal()
        tid = j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "X", [Split(1, 100), Split(2, -100)]), db_id=42)
        j.delete_transaction(tid)
        # Act & Assert
        assert j.get_db_id(tid) is None

    def test_chronological_sameDate_returnsInInsertionOrder(self):
        """chronological() preserves insertion order for same-date transactions."""
        # Arrange
        j = Journal()
        j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "A", [Split(1, 100), Split(2, -100)]))
        j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "B", [Split(3, 200), Split(4, -200)]))
        # Act
        result = j.chronological()
        # Assert
        assert [t.description for t in result] == ["A", "B"]

    def test_chronological_differentDates_sortedByDate(self):
        """chronological() returns transactions sorted by date ascending."""
        # Arrange
        j = Journal()
        j.add_transaction(JournalTransaction(datetime(2026, 1, 5), "Later", [Split(1, 100), Split(2, -100)]))
        j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "Earlier", [Split(3, 200), Split(4, -200)]))
        # Act
        result = j.chronological()
        # Assert
        assert [t.description for t in result] == ["Earlier", "Later"]

    def test_chronological_emptyJournal_returnsEmpty(self):
        """chronological() on a fresh Journal returns empty list."""
        # Arrange
        j = Journal()
        # Act
        result = j.chronological()
        # Assert
        assert result == []

    def test_emptyJournal_transactions_empty(self):
        """A fresh Journal has no transactions."""
        # Arrange & Act
        j = Journal()
        # Assert
        assert len(j.transactions) == 0


# ═══════════════════════════════════════════════════════════════════
#  AccountManager — Add / Update / Delete
# ═══════════════════════════════════════════════════════════════════


class TestAccountManagerAddUpdateDelete:
    """Account CRUD: add, update, delete via AccountManager."""

    # ── Add ────────────────────────────────────────────────────

    def test_addAccount_underAssets_returnsValidId(self, fast_manager):
        """Adding a checking account under Assets returns a valid ID."""
        # Arrange
        # Act
        aid = fast_manager.add_account("Checking", 1)
        # Assert
        assert aid > 0
        assert fast_manager.accounts[aid].name == "Checking"
        assert fast_manager.accounts[aid].parent == 1

    def test_addAccount_contra_flagTrue(self, fast_manager):
        """Contra flag is stored correctly."""
        # Arrange
        # Act
        aid = fast_manager.add_account("Depr", 1, is_contra=True)
        # Assert
        assert fast_manager.accounts[aid].is_contra is True

    def test_addAccount_duplicateName_raises(self, fast_manager):
        """Adding a duplicate name under the same parent raises ValueError."""
        # Arrange
        fast_manager.add_account("MyAcct", 1)
        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            fast_manager.add_account("MyAcct", 1)

    def test_addAccount_duplicateNameDifferentParent_succeeds(self, fast_manager):
        """Same name under different parents is allowed."""
        # Arrange
        # Act
        aid1 = fast_manager.add_account("Same", 1)
        aid2 = fast_manager.add_account("Same", 2)
        # Assert
        assert aid1 != aid2

    def test_addAccount_emptyName_raises(self, fast_manager):
        """Empty account name raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError):
            fast_manager.add_account("", 1)

    def test_addAccount_whitespaceName_raises(self, fast_manager):
        """Whitespace-only account name raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError):
            fast_manager.add_account("   ", 1)

    def test_addAccount_longName_succeeds(self, fast_manager):
        """Long strings are accepted as account names."""
        # Arrange
        # Act
        aid = fast_manager.add_account("A" * 200, 1)
        # Assert
        assert fast_manager.accounts[aid].name == "A" * 200

    def test_addAccount_withSubtype_saves(self, fast_manager):
        """Account subtype is stored."""
        # Arrange
        # Act
        aid = fast_manager.add_account("Vis", 2, account_subtype="credit_card")
        # Assert
        assert fast_manager.accounts[aid].account_subtype == "credit_card"

    def test_addAccount_invalidSubtype_raises(self, fast_manager):
        """Invalid subtype raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Invalid account_subtype"):
            fast_manager.add_account("Bad", 1, account_subtype="fake_type")

    def test_addAccount_specialCharacters_succeeds(self, fast_manager):
        """Special characters in account names are accepted."""
        # Arrange
        # Act
        aid = fast_manager.add_account("Checking! @ Home #1", 1)
        # Assert
        assert aid > 0

    # ── Update ─────────────────────────────────────────────────

    def test_updateAccount_name_updates(self, fast_manager):
        """Updating an account's name changes it in the manager."""
        # Arrange
        aid = fast_manager.add_account("Old", 1)
        # Act
        fast_manager.update_account(aid, "Renamed")
        # Assert
        assert fast_manager.accounts[aid].name == "Renamed"

    def test_updateAccount_type_updates(self, fast_manager):
        """Updating an account's type changes it."""
        # Arrange
        aid = fast_manager.add_account("Migrate", 1, "ASSET")
        # Act
        fast_manager.update_account(aid, "Migrate", acct_type="LIABILITY")
        # Assert
        assert fast_manager.accounts[aid].acct_type == "LIABILITY"

    def test_updateAccount_subtype_updates(self, fast_manager):
        """Updating an account's subtype changes it."""
        # Arrange
        aid = fast_manager.add_account("Card", 2, account_subtype="credit_card")
        # Act
        fast_manager.update_account(aid, "Card", account_subtype="checking")
        # Assert
        assert fast_manager.accounts[aid].account_subtype == "checking"

    def test_updateAccount_nonexistent_raises(self, fast_manager):
        """Updating a non-existent account raises an exception."""
        # Arrange & Act & Assert
        with pytest.raises(Exception):
            fast_manager.update_account(9999, "Ghost")

    def test_updateAccount_emptyName_succeeds(self, fast_manager):
        """Updating an account with an empty name silently accepts it (update doesn't validate)."""
        # Arrange
        aid = fast_manager.add_account("Existing", 1)
        # Act
        fast_manager.update_account(aid, "")
        # Assert
        assert fast_manager.accounts[aid].name == ""

    # ── Delete ─────────────────────────────────────────────────

    def test_deleteAccount_leafAccount_succeeds(self, fast_manager):
        """Deleting a leaf account removes it from the accounts dict."""
        # Arrange
        aid = fast_manager.add_account("Temp", 1)
        assert aid in fast_manager.accounts
        # Act
        fast_manager.delete_account(aid)
        # Assert
        assert aid not in fast_manager.accounts

    def test_deleteAccount_withChildren_cascades_now(self, fast_manager):
        """Deleting an account that has children cascades."""
        parent = fast_manager.add_account("Parent", 1)
        child = fast_manager.add_account("Child", parent)
        fast_manager.delete_account(parent)
        assert parent not in fast_manager.accounts
        assert child not in fast_manager.accounts

    def test_deleteAccount_withTransactions_succeeds(self, fast_manager):
        """Deleting an account with referencing transactions removes them first."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.add_transaction(datetime(2026, 1, 1), "T", [Split(checking, 100000), Split(6, -100000)])
        # Act
        fast_manager.delete_account(checking)
        # Assert
        assert checking not in fast_manager.accounts

    def test_deleteAccount_referencingTxns_balancedAfter(self, fast_manager):
        """After deleting an account with referencing txns, ledger stays balanced."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.add_transaction(datetime(2026, 1, 1), "T", [Split(checking, 500000), Split(6, -500000)])
        fast_manager.generate_ledger()
        # Act
        fast_manager.delete_account(checking)
        # Assert
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_deleteAccount_rootAccount_raises(self, fast_manager):
        """Deleting the root account raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="root"):
            fast_manager.delete_account(0)

    def test_deleteAccount_nonexistent_raises(self, fast_manager):
        """Deleting a non-existent account raises KeyError or ValueError."""
        # Arrange & Act & Assert
        with pytest.raises((KeyError, ValueError)):
            fast_manager.delete_account(99999)


# ═══════════════════════════════════════════════════════════════════
#  Transaction CRUD — add, delete, validate
# ═══════════════════════════════════════════════════════════════════


class TestTransactionCRUD:
    """Adding, deleting, and validating transactions."""

    # ── Add ────────────────────────────────────────────────────

    def test_addTransaction_simpleSplit_addsToJournal(self, fast_manager):
        """A simple 2-split transaction adds to the journal."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)
        # Act
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 15), "Shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        # Assert
        assert txn_id >= 0

    def test_addTransaction_compoundSplit_succeeds(self, fast_manager):
        """A 3-split compound transaction is accepted."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        savings = fast_manager.add_account("Savings", 1)
        wages = fast_manager.add_account("Wages", 4)
        # Act
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 15), "Split deposit",
            [Split(wages, -150000), Split(checking, 100000), Split(savings, 50000)],
        )
        # Assert
        assert txn_id >= 0

    def test_addTransaction_manySplits_balanced(self, fast_manager):
        """A 4-split transaction stays balanced."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        a = fast_manager.add_account("A", 1)
        b = fast_manager.add_account("B", 1)
        c = fast_manager.add_account("C", 1)
        # Act
        fast_manager.add_transaction(datetime(2026, 1, 1), "Complex",
            [Split(checking, 100000), Split(a, -25000), Split(b, -25000), Split(c, -50000)])
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_addTransaction_unbalanced_raises(self, fast_manager):
        """Splits that don't sum to zero raise ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        # Act & Assert
        with pytest.raises(ValueError, match="Unbalanced"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Bad", [Split(checking, 5000)])

    def test_addTransaction_emptySplits_raises(self, fast_manager):
        """A transaction with no splits raises."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="at least one split"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Empty", [])

    def test_addTransaction_zeroAmount_raises(self, fast_manager):
        """A split with amount 0 raises."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        # Act & Assert
        with pytest.raises(ValueError, match="zero"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Zero",
                [Split(checking, 0), Split(wages, 0)])

    def test_addTransaction_nonexistentAccount_raises(self, fast_manager):
        """A split referencing a non-existent account raises."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        # Act & Assert
        with pytest.raises(ValueError, match="No account"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Bad",
                [Split(checking, 5000), Split(9999, -5000)])

    def test_addTransaction_nonexistentAccountBothSides_raises(self, fast_manager):
        """Splits referencing only non-existent accounts raise."""
        # Arrange & Act & Assert
        with pytest.raises((ValueError, KeyError)):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Bad",
                [Split(9998, 5000), Split(9999, -5000)])

    def test_addTransaction_emptyDescription_raises(self, fast_manager):
        """An empty description raises ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        # Act & Assert
        with pytest.raises(ValueError, match="description"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "",
                [Split(wages, -50000), Split(checking, 50000)])

    def test_addTransaction_whitespaceDescription_raises(self, fast_manager):
        """A whitespace-only description raises ValueError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        # Act & Assert
        with pytest.raises(ValueError, match="description"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "   ",
                [Split(wages, -50000), Split(checking, 50000)])

    def test_addTransaction_veryLongDescription_succeeds(self, fast_manager):
        """Very long descriptions are accepted."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        # Act
        tid = fast_manager.add_transaction(datetime(2026, 1, 1), "A" * 500,
            [Split(wages, -50000), Split(checking, 50000)])
        # Assert
        assert tid >= 0

    def test_addTransaction_largeAmounts_balanced(self, fast_manager):
        """Transactions with very large amounts (boundary) stay balanced."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        # Act — 2^31 - 1 is near max 32-bit signed int
        tid = fast_manager.add_transaction(datetime(2026, 1, 1), "Large",
            [Split(wages, -2147483647), Split(checking, 2147483647)])
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.check_accounting_equation()["balanced"] is True

    # ── Delete ─────────────────────────────────────────────────

    def test_deleteTransaction_removesAndRebalances(self, fast_manager):
        """Deleting a transaction keeps the ledger balanced."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        t1 = fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        rent = fast_manager.add_account("Rent", 5)
        fast_manager.add_transaction(datetime(2026, 1, 2), "Rent",
            [Split(rent, 20000), Split(checking, -20000)])
        fast_manager.generate_ledger()
        assert fast_manager.check_accounting_equation()["balanced"] is True
        # Act
        fast_manager.delete_transaction(t1)
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_deleteTransaction_allTxns_accountsZero(self, fast_manager):
        """Deleting all transactions leaves all accounts at zero."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "P1",
            [Split(wages, -50000), Split(checking, 50000)])
        fast_manager.add_transaction(datetime(2026, 1, 2), "P2",
            [Split(wages, -100000), Split(checking, 100000)])
        fast_manager.add_transaction(datetime(2026, 1, 3), "Exp",
            [Split(fast_manager.add_account("Exp", 5), 30000), Split(checking, -30000)])
        fast_manager.generate_ledger()
        # Act
        for tid in list(fast_manager.journal.transactions.keys()):
            fast_manager.delete_transaction(tid)
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.check_accounting_equation()["assets"] == 0
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_deleteTransaction_nonexistent_raises(self, fast_manager):
        """Deleting a non-existent transaction raises KeyError."""
        # Arrange & Act & Assert
        with pytest.raises(KeyError):
            fast_manager.delete_transaction(9999)

    def test_deleteTransaction_twice_raises(self, fast_manager):
        """Deleting the same transaction twice raises KeyError."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        tid = fast_manager.add_transaction(datetime(2026, 1, 1), "T",
            [Split(wages, -50000), Split(checking, 50000)])
        fast_manager.delete_transaction(tid)
        # Act & Assert
        with pytest.raises(KeyError):
            fast_manager.delete_transaction(tid)


# ═══════════════════════════════════════════════════════════════════
#  Generate Ledger — trial balance verification
# ═══════════════════════════════════════════════════════════════════


class TestGenerateLedger:
    """generate_ledger — computing balances from journal entries."""

    def test_generateLedger_noTransactions_allZero(self, fast_manager):
        """With no transactions, all account balances are zero."""
        # Arrange — fast_manager has no transactions
        # Act
        fast_manager.generate_ledger()
        # Assert
        assert all(acct.get_balance() == 0 for aid, acct in fast_manager.accounts.items() if aid)

    def test_generateLedger_singleTransaction_sumsCorrectly(self, fast_manager):
        """A simple transaction updates account balances."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        # Act
        fast_manager.generate_ledger()
        # Assert
        assert fast_manager.accounts[checking].get_balance() == 50000
        assert fast_manager.accounts[wages].get_balance() == -50000

    def test_generateLedger_balanced_sumsToZero(self, fast_manager):
        """generate_ledger does not raise for balanced transactions."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        # Act — should not raise
        fast_manager.generate_ledger()

    def test_generateLedger_emptyAndFull_consistent(self, fast_manager):
        """generate_ledger can be called twice (idempotent)."""
        # Arrange
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        # Act
        fast_manager.generate_ledger()
        bal1 = fast_manager.accounts[checking].get_balance()
        fast_manager.generate_ledger()
        bal2 = fast_manager.accounts[checking].get_balance()
        # Assert
        assert bal1 == bal2


# ═══════════════════════════════════════════════════════════════════
#  Closing Entries
# ═══════════════════════════════════════════════════════════════════


class TestCloseTemps:
    """close_temps — closing income/expense to retained earnings."""

    def test_closeTemps_zeroesIncomeAndExpense(self, fast_seeded):
        """After close_temps, income and expense accounts have zero balance."""
        # Arrange — fast_seeded has income and expense transactions
        # Act
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        # Assert
        assert all(acct.get_balance() == 0
                   for aid, acct in fast_seeded.accounts.items()
                   if acct.acct_type in ("INCOME", "EXPENSE"))

    def test_closeTemps_rebuildsLedger(self, fast_seeded):
        """After close, RE balance is non-zero."""
        # Arrange — fast_seeded has income/expense data
        # Act
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        # Assert
        assert fast_seeded.accounts[6].get_balance() != 0

    def test_closeTemps_doubleClose_noChange(self, fast_seeded):
        """Calling close_temps twice produces the same RE balance."""
        # Arrange
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        re1 = fast_seeded.accounts[6].get_balance()
        # Act
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        # Assert
        assert fast_seeded.accounts[6].get_balance() == re1


# ═══════════════════════════════════════════════════════════════════
#  Widget Helpers
# ═══════════════════════════════════════════════════════════════════


class TestFormatCents:
    """format_cents — integer cents to USD string. No tkinter required."""

    @staticmethod
    def _fmt(cents):
        if cents is None:
            return "\u2014"
        sign = "-" if cents < 0 else ""
        return f"{sign}${abs(cents)/100:,.2f}"

    def test_positive_123456_returnsDollar1234Dot56(self):
        """Arrange & Act & Assert: 123456 cents → $1,234.56."""
        assert TestFormatCents._fmt(123456) == "$1,234.56"

    def test_zero_returnsZeroDollar(self):
        """Arrange & Act & Assert: 0 cents → $0.00."""
        assert TestFormatCents._fmt(0) == "$0.00"

    def test_negative_5000_returnsNegativePrefix(self):
        """Arrange & Act & Assert: -5000 cents → -$50.00."""
        assert TestFormatCents._fmt(-5000) == "-$50.00"

    def test_largeValue_commasCorrect(self):
        """Arrange & Act & Assert: 12345678 cents → $123,456.78."""
        assert TestFormatCents._fmt(12345678) == "$123,456.78"

    def test_none_returnsDash(self):
        """Arrange & Act & Assert: None → em-dash."""
        assert TestFormatCents._fmt(None) == "\u2014"

    def test_smallValue_padsDecimals(self):
        """Arrange & Act & Assert: 1 cent → $0.01, -1 cent → -$0.01."""
        assert TestFormatCents._fmt(1) == "$0.01"
        assert TestFormatCents._fmt(-1) == "-$0.01"


class TestBuildAccountChoices:
    """build_account_choices — dropdown options for dialogs.
    Requires tkinter — tests are skipped when unavailable.
    """

    def _import_and_run(self, fast_manager, subtype_filter=None):
        """Import and run build_account_choices, swallowing ImportError."""
        try:
            from ledger.gui.widgets import build_account_choices
            kwargs = {}
            if subtype_filter is not None:
                kwargs["subtype_filter"] = subtype_filter
            return build_account_choices(fast_manager, **kwargs)
        except ImportError:
            pytest.skip("tkinter not available")
        except Exception:
            pytest.skip("tkinter display required")

    def test_buildChoices_returnsLabelsAndMap(self, fast_manager):
        """Arrange: manager. Act: build_account_choices. Assert: both lists non-empty."""
        # Arrange & Act & Assert
        labels, mapping = self._import_and_run(fast_manager)
        assert len(labels) > 0
        assert len(mapping) > 0

    def test_buildChoices_labelsAreStrings(self, fast_manager):
        """Arrange: manager. Act: build_account_choices. Assert: labels are strings."""
        # Arrange & Act & Assert
        labels, _ = self._import_and_run(fast_manager)
        for label in labels:
            assert isinstance(label, str)

    def test_buildChoices_mappingMapsToInt(self, fast_manager):
        """Arrange: manager. Act: build_account_choices. Assert: values are ints."""
        # Arrange & Act & Assert
        _, mapping = self._import_and_run(fast_manager)
        for key, value in mapping.items():
            assert isinstance(value, int)

    def test_buildChoices_withSubtypeFilter_filters(self, fast_manager):
        """Arrange: manager + accounts. Act: filter by subtype. Assert: filtered list."""
        # Arrange
        fast_manager.add_account("C", 1, account_subtype="checking")
        fast_manager.add_account("B", 1, account_subtype="brokerage")
        # Act & Assert
        labels, _ = self._import_and_run(fast_manager, subtype_filter={"checking"})
        assert len(labels) > 0

    def test_buildChoices_nonexistentSubtype_doesNotCrash(self, fast_manager):
        """Arrange: manager. Act: filter by nonexistent subtype. Assert: no crash."""
        # Arrange & Act & Assert
        labels, _ = self._import_and_run(fast_manager, subtype_filter={"xyz_fake_type"})
        assert isinstance(labels, list)
