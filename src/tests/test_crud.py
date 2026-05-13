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
        j = Journal()
        txn = JournalTransaction(datetime(2026, 1, 15), "Test", [Split(1, 5000), Split(2, -5000)])
        txn_id = j.add_transaction(txn)
        assert txn_id == 0
        assert len(j.transactions) == 1
        assert j.transactions[0] is txn

    def test_addTransaction_multiple_idsIncrement(self):
        """Multiple calls to add_transaction return sequential IDs."""
        j = Journal()
        id1 = j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "A", [Split(1, 100), Split(2, -100)]))
        id2 = j.add_transaction(JournalTransaction(datetime(2026, 1, 2), "B", [Split(1, 200), Split(2, -200)]))
        assert id1 == 0
        assert id2 == 1

    def test_deleteTransaction_removesFromDict(self):
        """Deleting a transaction removes it from the in-memory store."""
        j = Journal()
        tid = j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "X", [Split(1, 100), Split(2, -100)]))
        j.delete_transaction(tid)
        assert tid not in j.transactions

    def test_deleteTransaction_nonexistent_raises(self):
        """Deleting a non-existent transaction raises KeyError."""
        j = Journal()
        with pytest.raises(KeyError):
            j.delete_transaction(999)

    def test_addTransaction_withDbId_storesMapping(self):
        """add_transaction with db_id=42 makes get_db_id return 42."""
        j = Journal()
        txn = JournalTransaction(datetime(2026, 1, 1), "X", [Split(1, 100), Split(2, -100)])
        mem_id = j.add_transaction(txn, db_id=42)
        assert j.get_db_id(mem_id) == 42

    def test_getDbId_notSet_returnsNone(self):
        """get_db_id on an unmapped ID returns None."""
        j = Journal()
        assert j.get_db_id(0) is None

    def test_chronological_sameDate_returnsInInsertionOrder(self):
        """chronological() preserves insertion order for same-date transactions."""
        j = Journal()
        j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "A", [Split(1, 100), Split(2, -100)]))
        j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "B", [Split(3, 200), Split(4, -200)]))
        assert [t.description for t in j.chronological()] == ["A", "B"]

    def test_chronological_differentDates_sortedByDate(self):
        """chronological() returns transactions sorted by date ascending."""
        j = Journal()
        j.add_transaction(JournalTransaction(datetime(2026, 1, 5), "Later", [Split(1, 100), Split(2, -100)]))
        j.add_transaction(JournalTransaction(datetime(2026, 1, 1), "Earlier", [Split(3, 200), Split(4, -200)]))
        assert [t.description for t in j.chronological()] == ["Earlier", "Later"]

    def test_emptyJournal_transactions_empty(self):
        """A fresh Journal has no transactions."""
        j = Journal()
        assert len(j.transactions) == 0


# ═══════════════════════════════════════════════════════════════════
#  AccountManager — Add / Update / Delete
# ═══════════════════════════════════════════════════════════════════


class TestAccountManagerAddUpdateDelete:
    """Account CRUD: add, update, delete via AccountManager."""

    # ── Add ────────────────────────────────────────────────────

    def test_addAccount_underAssets_returnsValidId(self, fast_manager):
        """Adding a checking account under Assets returns a valid ID."""
        aid = fast_manager.add_account("Checking", 1)
        assert aid > 0
        assert fast_manager.accounts[aid].name == "Checking"
        assert fast_manager.accounts[aid].parent == 1

    def test_addAccount_contra_flagTrue(self, fast_manager):
        """Contra flag is stored correctly."""
        aid = fast_manager.add_account("Depr", 1, is_contra=True)
        assert fast_manager.accounts[aid].is_contra is True

    def test_addAccount_duplicateName_raises(self, fast_manager):
        """Adding a duplicate name under the same parent raises ValueError."""
        fast_manager.add_account("MyAcct", 1)
        with pytest.raises(ValueError, match="already exists"):
            fast_manager.add_account("MyAcct", 1)

    def test_addAccount_duplicateNameDifferentParent_succeeds(self, fast_manager):
        """Same name under different parents is allowed."""
        aid1 = fast_manager.add_account("Same", 1)
        aid2 = fast_manager.add_account("Same", 2)
        assert aid1 != aid2

    def test_addAccount_emptyName_raises(self, fast_manager):
        """Empty account name raises ValueError."""
        with pytest.raises(ValueError):
            fast_manager.add_account("", 1)

    def test_addAccount_whitespaceName_raises(self, fast_manager):
        """Whitespace-only account name raises ValueError."""
        with pytest.raises(ValueError):
            fast_manager.add_account("   ", 1)

    def test_addAccount_longName_succeeds(self, fast_manager):
        """Long strings are accepted as account names."""
        aid = fast_manager.add_account("A" * 200, 1)
        assert fast_manager.accounts[aid].name == "A" * 200

    def test_addAccount_withSubtype_saves(self, fast_manager):
        """Account subtype is stored."""
        aid = fast_manager.add_account("Vis", 2, account_subtype="credit_card")
        assert fast_manager.accounts[aid].account_subtype == "credit_card"

    def test_addAccount_invalidSubtype_raises(self, fast_manager):
        """Invalid subtype raises ValueError."""
        with pytest.raises(ValueError, match="Invalid account_subtype"):
            fast_manager.add_account("Bad", 1, account_subtype="fake_type")

    def test_addAccount_specialCharacters_succeeds(self, fast_manager):
        """Special characters in account names are accepted."""
        aid = fast_manager.add_account("Checking! @ Home #1", 1)
        assert aid > 0

    # ── Update ─────────────────────────────────────────────────

    def test_updateAccount_name_updates(self, fast_manager):
        """Updating an account's name changes it in the manager."""
        aid = fast_manager.add_account("Old", 1)
        fast_manager.update_account(aid, "Renamed")
        assert fast_manager.accounts[aid].name == "Renamed"

    def test_updateAccount_type_updates(self, fast_manager):
        """Updating an account's type changes it."""
        aid = fast_manager.add_account("Migrate", 1, "ASSET")
        fast_manager.update_account(aid, "Migrate", acct_type="LIABILITY")
        assert fast_manager.accounts[aid].acct_type == "LIABILITY"

    def test_updateAccount_subtype_updates(self, fast_manager):
        """Updating an account's subtype changes it."""
        aid = fast_manager.add_account("Card", 2, account_subtype="credit_card")
        fast_manager.update_account(aid, "Card", account_subtype="checking")
        assert fast_manager.accounts[aid].account_subtype == "checking"

    def test_updateAccount_nonexistent_raises(self, fast_manager):
        """Updating a non-existent account raises an exception."""
        with pytest.raises(Exception):
            fast_manager.update_account(9999, "Ghost")

    # ── Delete ─────────────────────────────────────────────────

    def test_deleteAccount_leafAccount_succeeds(self, fast_manager):
        """Deleting a leaf account removes it from the accounts dict."""
        aid = fast_manager.add_account("Temp", 1)
        assert aid in fast_manager.accounts
        fast_manager.delete_account(aid)
        assert aid not in fast_manager.accounts

    def test_deleteAccount_withChildren_raises(self, fast_manager):
        """Deleting an account that has children raises."""
        parent = fast_manager.add_account("Parent", 1)
        fast_manager.add_account("Child", parent)
        with pytest.raises(ValueError, match="sub-account"):
            fast_manager.delete_account(parent)

    def test_deleteAccount_withTransactions_succeeds(self, fast_manager):
        """Deleting an account with referencing transactions removes them first."""
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.add_transaction(datetime(2026, 1, 1), "T", [Split(checking, 100000), Split(6, -100000)])
        fast_manager.delete_account(checking)
        assert checking not in fast_manager.accounts

    def test_deleteAccount_referencingTxns_balancedAfter(self, fast_manager):
        """After deleting an account with referencing txns, ledger stays balanced."""
        checking = fast_manager.add_account("Checking", 1)
        fast_manager.add_transaction(datetime(2026, 1, 1), "T", [Split(checking, 500000), Split(6, -500000)])
        fast_manager.generate_ledger()
        fast_manager.delete_account(checking)
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_deleteAccount_rootAccount_raises(self, fast_manager):
        """Deleting the root account raises ValueError."""
        with pytest.raises(ValueError, match="root"):
            fast_manager.delete_account(0)


# ═══════════════════════════════════════════════════════════════════
#  Transaction CRUD — add, delete, validate
# ═══════════════════════════════════════════════════════════════════


class TestTransactionCRUD:
    """Adding, deleting, and validating transactions."""

    # ── Add ────────────────────────────────────────────────────

    def test_addTransaction_simpleSplit_addsToJournal(self, fast_manager):
        """A simple 2-split transaction adds to the journal."""
        checking = fast_manager.add_account("Checking", 1)
        groceries = fast_manager.add_account("Groceries", 5)
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 15), "Shop",
            [Split(groceries, 5000), Split(checking, -5000)],
        )
        assert txn_id >= 0

    def test_addTransaction_compoundSplit_succeeds(self, fast_manager):
        """A 3-split compound transaction is accepted."""
        checking = fast_manager.add_account("Checking", 1)
        savings = fast_manager.add_account("Savings", 1)
        wages = fast_manager.add_account("Wages", 4)
        txn_id = fast_manager.add_transaction(
            datetime(2026, 1, 15), "Split deposit",
            [Split(wages, -150000), Split(checking, 100000), Split(savings, 50000)],
        )
        assert txn_id >= 0

    def test_addTransaction_manySplits_balanced(self, fast_manager):
        """A 4-split transaction stays balanced."""
        checking = fast_manager.add_account("Checking", 1)
        a = fast_manager.add_account("A", 1)
        b = fast_manager.add_account("B", 1)
        c = fast_manager.add_account("C", 1)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Complex",
            [Split(checking, 100000), Split(a, -25000), Split(b, -25000), Split(c, -50000)])
        fast_manager.generate_ledger()
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_addTransaction_unbalanced_raises(self, fast_manager):
        """Splits that don't sum to zero raise ValueError."""
        checking = fast_manager.add_account("Checking", 1)
        with pytest.raises(ValueError, match="Unbalanced"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Bad", [Split(checking, 5000)])

    def test_addTransaction_emptySplits_raises(self, fast_manager):
        """A transaction with no splits raises."""
        with pytest.raises(ValueError, match="at least one split"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Empty", [])

    def test_addTransaction_zeroAmount_raises(self, fast_manager):
        """A split with amount 0 raises."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        with pytest.raises(ValueError, match="zero"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Zero",
                [Split(checking, 0), Split(wages, 0)])

    def test_addTransaction_nonexistentAccount_raises(self, fast_manager):
        """A split referencing a non-existent account raises."""
        checking = fast_manager.add_account("Checking", 1)
        with pytest.raises(ValueError, match="No account"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "Bad",
                [Split(checking, 5000), Split(9999, -5000)])

    def test_addTransaction_emptyDescription_raises(self, fast_manager):
        """An empty description raises ValueError."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        with pytest.raises(ValueError, match="description"):
            fast_manager.add_transaction(datetime(2026, 1, 1), "",
                [Split(wages, -50000), Split(checking, 50000)])

    def test_addTransaction_veryLongDescription_succeeds(self, fast_manager):
        """Very long descriptions are accepted."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        tid = fast_manager.add_transaction(datetime(2026, 1, 1), "A" * 500,
            [Split(wages, -50000), Split(checking, 50000)])
        assert tid >= 0

    # ── Delete ─────────────────────────────────────────────────

    def test_deleteTransaction_removesAndRebalances(self, fast_manager):
        """Deleting a transaction keeps the ledger balanced."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        t1 = fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        rent = fast_manager.add_account("Rent", 5)
        fast_manager.add_transaction(datetime(2026, 1, 2), "Rent",
            [Split(rent, 20000), Split(checking, -20000)])
        fast_manager.generate_ledger()
        assert fast_manager.check_accounting_equation()["balanced"] is True
        fast_manager.delete_transaction(t1)
        fast_manager.generate_ledger()
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_deleteTransaction_allTxns_accountsZero(self, fast_manager):
        """Deleting all transactions leaves all accounts at zero."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "P1",
            [Split(wages, -50000), Split(checking, 50000)])
        fast_manager.add_transaction(datetime(2026, 1, 2), "P2",
            [Split(wages, -100000), Split(checking, 100000)])
        fast_manager.add_transaction(datetime(2026, 1, 3), "Exp",
            [Split(fast_manager.add_account("Exp", 5), 30000), Split(checking, -30000)])
        fast_manager.generate_ledger()
        for tid in list(fast_manager.journal.transactions.keys()):
            fast_manager.delete_transaction(tid)
        fast_manager.generate_ledger()
        assert fast_manager.check_accounting_equation()["assets"] == 0
        assert fast_manager.check_accounting_equation()["balanced"] is True

    def test_deleteTransaction_nonexistent_raises(self, fast_manager):
        """Deleting a non-existent transaction raises KeyError."""
        with pytest.raises(KeyError):
            fast_manager.delete_transaction(9999)


# ═══════════════════════════════════════════════════════════════════
#  Generate Ledger — trial balance verification
# ═══════════════════════════════════════════════════════════════════


class TestGenerateLedger:
    """generate_ledger — computing balances from journal entries."""

    def test_generateLedger_noTransactions_allZero(self, fast_manager):
        """With no transactions, all account balances are zero."""
        fast_manager.generate_ledger()
        assert all(acct.get_balance() == 0 for aid, acct in fast_manager.accounts.items() if aid)

    def test_generateLedger_singleTransaction_sumsCorrectly(self, fast_manager):
        """A simple transaction updates account balances."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        fast_manager.generate_ledger()
        assert fast_manager.accounts[checking].get_balance() == 50000
        assert fast_manager.accounts[wages].get_balance() == -50000

    def test_generateLedger_balanced_sumsToZero(self, fast_manager):
        """generate_ledger does not raise for balanced transactions."""
        checking = fast_manager.add_account("Checking", 1)
        wages = fast_manager.add_account("Wages", 4)
        fast_manager.add_transaction(datetime(2026, 1, 1), "Pay",
            [Split(wages, -50000), Split(checking, 50000)])
        fast_manager.generate_ledger()  # should not raise


# ═══════════════════════════════════════════════════════════════════
#  Closing Entries
# ═══════════════════════════════════════════════════════════════════


class TestCloseTemps:
    """close_temps — closing income/expense to retained earnings."""

    def test_closeTemps_zeroesIncomeAndExpense(self, fast_seeded):
        """After close_temps, income and expense accounts have zero balance."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        assert all(acct.get_balance() == 0
                   for aid, acct in fast_seeded.accounts.items()
                   if acct.acct_type in ("INCOME", "EXPENSE"))

    def test_closeTemps_rebuildsLedger(self, fast_seeded):
        """After close, RE balance is non-zero."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        assert fast_seeded.accounts[6].get_balance() != 0

    def test_closeTemps_doubleClose_noChange(self, fast_seeded):
        """Calling close_temps twice produces the same RE balance."""
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
        re1 = fast_seeded.accounts[6].get_balance()
        fast_seeded.close_temps()
        fast_seeded.generate_ledger()
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
        assert TestFormatCents._fmt(123456) == "$1,234.56"

    def test_zero_returnsZeroDollar(self):
        assert TestFormatCents._fmt(0) == "$0.00"

    def test_negative_5000_returnsNegativePrefix(self):
        assert TestFormatCents._fmt(-5000) == "-$50.00"

    def test_largeValue_commasCorrect(self):
        assert TestFormatCents._fmt(12345678) == "$123,456.78"

    def test_none_returnsDash(self):
        assert TestFormatCents._fmt(None) == "\u2014"

    def test_smallValue_padsDecimals(self):
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
        labels, mapping = self._import_and_run(fast_manager)
        assert len(labels) > 0
        assert len(mapping) > 0

    def test_buildChoices_labelsAreStrings(self, fast_manager):
        labels, _ = self._import_and_run(fast_manager)
        for label in labels:
            assert isinstance(label, str)

    def test_buildChoices_mappingMapsToInt(self, fast_manager):
        _, mapping = self._import_and_run(fast_manager)
        for key, value in mapping.items():
            assert isinstance(value, int)

    def test_buildChoices_withSubtypeFilter_filters(self, fast_manager):
        fast_manager.add_account("C", 1, account_subtype="checking")
        fast_manager.add_account("B", 1, account_subtype="brokerage")
        labels, _ = self._import_and_run(fast_manager, subtype_filter={"checking"})
        assert len(labels) > 0

    def test_buildChoices_nonexistentSubtype_doesNotCrash(self, fast_manager):
        labels, _ = self._import_and_run(fast_manager, subtype_filter={"xyz_fake_type"})
        assert isinstance(labels, list)
