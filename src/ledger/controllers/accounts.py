from __future__ import annotations

from datetime import datetime

from ..constants import PARENTS, DATE_STR
from ..database.database_controller import DatabaseController
from ..models.data_books import Ledger, Journal
from ..models.data_class import JournalTransaction

DEFAULT_DB_PATH = "data/journal.db"


class Account:
    def __init__(self, name: str, parent: int | None = None):
        self.name = name
        self.parent = parent
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

    def _load_state(self):
        """Load accounts and transactions from the database into memory."""
        db_accounts = self.db.load_accounts()

        if not db_accounts:
            # First run — seed the parent accounts
            self._generate_parents()
        else:
            for acct_id, name, parent_id in db_accounts:
                # Virtual root (id 0) doesn't exist in DB, so NULL parent = root child
                parent = parent_id if parent_id is not None else 0
                self.accounts[acct_id] = Account(name, parent)

            for _, date_str, desc, credit_id, debit_id, amount in self.db.load_transactions():
                date = datetime.strptime(date_str, DATE_STR)
                txn = JournalTransaction(date, desc, credit_id, debit_id, amount)
                self.journal.add_transaction(txn)

        self.account_num = max(self.accounts.keys()) + 1

    def _generate_parents(self):
        """Create the top-level parent accounts (assets, liabilities, etc.)."""
        for name in PARENTS:
            self.add_account(name, 0)

    def add_transaction(
        self,
        date: datetime,
        description: str,
        credit_acct: int,
        debit_acct: int,
        amount: int,
    ) -> int:
        if credit_acct not in self.accounts:
            raise ValueError(f"No account {credit_acct}")
        if debit_acct not in self.accounts:
            raise ValueError(f"No account {debit_acct}")

        # Persist to database
        date_str = date.strftime(DATE_STR)
        self.db.save_transaction(date_str, description, credit_acct, debit_acct, amount)

        # Add to in-memory journal
        txn = JournalTransaction(date, description, credit_acct, debit_acct, amount)
        return self.journal.add_transaction(txn)

    def add_account(self, name: str, parent: int | None = None) -> int:
        if name in [a.name for a in self.accounts.values()]:
            raise ValueError(f"Account '{name}' already exists")

        # Virtual root (0) maps to NULL in the database
        db_parent = parent if parent != 0 else None
        acct_id = self.db.save_account(name, db_parent)
        self.accounts[acct_id] = Account(name, parent)
        return acct_id

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

    def build_tree(self):
        tree = {}
        for key, account in self.accounts.items():
            if account.parent is not None:
                if account.parent not in tree:
                    tree[account.parent] = [key]
                else:
                    tree[account.parent].append(key)
        return tree

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
