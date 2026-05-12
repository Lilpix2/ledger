"""
Business logic: Account model and AccountManager.
"""

from __future__ import annotations

from datetime import datetime

from ..constants import PARENTS, ACCT_TYPE_MAP, DATE_STR
from ..database.database_controller import DatabaseController
from ..models.data_books import Ledger, Journal
from ..models.data_class import JournalTransaction

DEFAULT_DB_PATH = "data/journal.db"

# Account types and their normal balance direction.
# Debit-normal: ASSET, EXPENSE  (debits increase the balance)
# Credit-normal: LIABILITY, EQUITY, INCOME  (credits increase the balance)
DEBIT_NORMAL_TYPES = frozenset({"ASSET", "EXPENSE"})


class Account:
    def __init__(self, name: str, parent: int | None = None, acct_type: str = "ASSET"):
        self.name = name
        self.parent = parent
        self.acct_type = acct_type
        self.ledger = Ledger()

    def __eq__(self, value):
        return self.name == value.name if isinstance(value, Account) else False

    def __repr__(self):
        return f"{self.name}, {self.get_balance()}"

    def get_balance(self) -> int:
        return self.ledger.balance


class AccountManager:

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.journal = Journal()
        self.accounts: dict[int, Account] = {0: Account("root")}
        self.db = DatabaseController(db_path)
        self.db.ensure_tables()
        self._load_state()

    # ── Init / Load ─────────────────────────────────────────────────

    def _load_state(self):
        """Load accounts and transactions from the database into memory."""
        db_accounts = self.db.load_accounts()

        if not db_accounts:
            self._generate_parents()
        else:
            for acct_id, name, parent_id, acct_type in db_accounts:
                parent = parent_id if parent_id is not None else 0
                self.accounts[acct_id] = Account(name, parent, acct_type)

            for _, date_str, desc, credit_id, debit_id, amount in self.db.load_transactions():
                date = datetime.strptime(date_str, DATE_STR)
                txn = JournalTransaction(date, desc, credit_id, debit_id, amount)
                self.journal.add_transaction(txn)

        self.account_num = max(self.accounts.keys()) + 1

    def _generate_parents(self):
        """Create the top-level parent accounts (assets, liabilities, etc.)."""
        for name in PARENTS:
            acct_type = ACCT_TYPE_MAP.get(name, "ASSET")
            self.add_account(name, 0, acct_type)

    # ── Accounts ────────────────────────────────────────────────────

    def add_account(
        self, name: str, parent: int | None = None, acct_type: str | None = None
    ) -> int:
        if name in [a.name for a in self.accounts.values()]:
            raise ValueError(f"Account '{name}' already exists")

        # Inherit type from parent if not explicitly provided
        if acct_type is None and parent is not None and parent in self.accounts:
            acct_type = self.accounts[parent].acct_type
        elif acct_type is None:
            acct_type = "ASSET"

        db_parent = parent if parent != 0 else None
        acct_id = self.db.save_account(name, db_parent, acct_type)
        self.accounts[acct_id] = Account(name, parent, acct_type)
        return acct_id

    # ── Transactions ────────────────────────────────────────────────

    def add_transaction(
        self,
        date: datetime,
        description: str,
        credit_acct: int,
        debit_acct: int,
        amount: int,
    ) -> int:
        # --- Pre-commit validation (double-entry integrity) ---
        if amount <= 0:
            raise ValueError("Transaction amount must be positive")
        if credit_acct not in self.accounts:
            raise ValueError(f"No account with ID {credit_acct}")
        if debit_acct not in self.accounts:
            raise ValueError(f"No account with ID {debit_acct}")
        if credit_acct == debit_acct:
            raise ValueError("Credit and debit accounts must be different")

        # Persist to database
        date_str = date.strftime(DATE_STR)
        self.db.save_transaction(date_str, description, credit_acct, debit_acct, amount)

        # Add to in-memory journal
        txn = JournalTransaction(date, description, credit_acct, debit_acct, amount)
        return self.journal.add_transaction(txn)

    # ── Ledger Generation ──────────────────────────────────────────

    def generate_ledger(self):
        for acct in self.accounts.values():
            acct.ledger.clear_entries()
        for txn in self.journal.chronological():
            self.accounts[txn.debit_acct].ledger.add_entry(
                txn.date,
                txn.description,
                0,
                txn.amount,
            )
            self.accounts[txn.credit_acct].ledger.add_entry(
                txn.date,
                txn.description,
                txn.amount,
                0,
            )
        total = 0
        for account in self.accounts.values():
            total += account.get_balance()
        if total != 0:
            raise Exception(f"Trial Balance is {total}. Book is unbalanced")

    # ── Tree / Hierarchy ───────────────────────────────────────────

    def build_tree(self):
        tree: dict[int, list[int]] = {}
        for key, account in self.accounts.items():
            if account.parent is not None:
                if account.parent not in tree:
                    tree[account.parent] = [key]
                else:
                    tree[account.parent].append(key)
        return tree

    def get_descendant_ids(self, account_id: int) -> set[int]:
        """Return ``{account_id} ∪ {all descendant account IDs}``."""
        ids: set[int] = {account_id}
        tree = self.build_tree()

        def walk(aid: int) -> None:
            for cid in tree.get(aid, []):
                ids.add(cid)
                walk(cid)

        walk(account_id)
        return ids

    def _print_tree(self, tree, node, dashes):
        for item in tree[node]:
            if tree.get(item, None) is not None:
                self._print_tree(tree, item, dashes + 1)
            else:
                print("-" * dashes + str(self.accounts[item]))

    def print_tree(self):
        tree = self.build_tree()
        for item in tree[0]:
            print(self.accounts[item])
            if tree.get(item, None) is not None:
                self._print_tree(tree, item, 1)

    # ── Balances ────────────────────────────────────────────────────

    def aggregated_balance(self, account_id: int) -> int:
        """Sum the *raw* balance of an account and all its descendants."""
        total = self.accounts[account_id].get_balance()
        tree = self.build_tree()
        for child_id in tree.get(account_id, []):
            total += self.aggregated_balance(child_id)
        return total

    # ── Normal Balance Logic ────────────────────────────────────────

    def get_top_level_parent(self, account_id: int) -> int:
        """Walk up to find the top-level parent (direct child of root).

        Returns the account ID of the top-level parent, or *account_id*
        itself if it is already a top-level account.
        """
        if account_id == 0:
            return 0
        current = account_id
        while True:
            parent = self.accounts[current].parent
            if parent is None or parent == 0:
                return current
            current = parent

    def is_debit_normal(self, account_id: int) -> bool:
        """Return ``True`` if *account_id* is debit-normal (ASSET or EXPENSE).

        O(1) — uses the stored `acct_type` directly instead of walking
        up the tree to find the top-level parent.
        """
        return self.accounts[account_id].acct_type in DEBIT_NORMAL_TYPES

    def get_display_balance(self, account_id: int) -> int:
        """Return the balance as a positive number in its **normal** direction.

        Debit-normal accounts (assets, expenses) display the raw balance
        directly.  Credit-normal accounts (liabilities, equity, income)
        have their sign flipped.
        """
        raw = self.aggregated_balance(account_id)
        if self.is_debit_normal(account_id):
            return raw
        return -raw

    # ── Financial Reports ───────────────────────────────────────────

    def check_accounting_equation(self) -> dict:
        """Return a snapshot of the accounting equation.

        Aggregates by `acct_type` (no tree-walking needed).

        Returns
        -------
        dict
            ``balanced`` (bool), ``assets``, ``liabilities``, ``equity``,
            ``net_income`` (income − expenses), ``net_worth`` (assets −
            liabilities), ``lhs`` (assets) and ``rhs`` (liabilities +
            equity + net_income) — all amounts in cents, **display-normal**.
        """
        raw: dict[str, int] = {
            "ASSET": 0, "LIABILITY": 0, "EQUITY": 0,
            "INCOME": 0, "EXPENSE": 0,
        }

        for acct_id, account in self.accounts.items():
            if acct_id == 0:
                continue
            raw[account.acct_type] += account.get_balance()

        # Convert raw → display-normal
        a = raw["ASSET"]                 # debit-normal
        l = -raw["LIABILITY"]            # credit-normal → flip
        e = -raw["EQUITY"]               # credit-normal → flip
        i = -raw["INCOME"]               # credit-normal → flip
        ex = raw["EXPENSE"]              # debit-normal

        net_income = i - ex
        rhs = l + e + net_income
        balanced = a == rhs

        return {
            "balanced": balanced,
            "assets": a,
            "liabilities": l,
            "equity": e,
            "net_income": net_income,
            "net_worth": a - l,
            "lhs": a,
            "rhs": rhs,
        }

    def get_net_worth(self) -> int:
        """Net worth in cents (display-normal)."""
        eq = self.check_accounting_equation()
        return eq["net_worth"]

    def gen_income_report(self):
        income_ids = self.get_descendant_ids(4) #4 is income base account
        expense_ids = self.get_descendant_ids(5)#5 is expense base account
        transactions = {'income':{},'expense':{}}
        id = 0
        credit = 0
        debit = 0
        for transaction in self.journal.transactions.values():
            if transaction.credit_acct in income_ids:
                transactions['income'][id] = transaction
                credit += transaction.amount
                id += 1
        for transaction in self.journal.transactions.values():
            if transaction.debit_acct in expense_ids:
                transactions['expense'][id] = transaction
                debit += transaction.amount
                id += 1
        print('----Income Report----')
        print('----Income----')
        for transaction in transactions["income"].values():
            print(f"{transaction.description}: {transaction.amount/100:.2f}")
        print(print('----Expenses----'))
        for transaction in transactions["expense"].values():
            print(f"{transaction.description}: {transaction.amount/100:.2f}")
        print('----total----')
        print(f'{(credit-debit)/100:.2f}')



