from __future__ import annotations
from .data_books import Ledger, Journal
from .data_class import JournalTransaction
from constants import PARENTS
from datetime import datetime

class Account:
    def __init__(self, name: str, parent: int | None = None):
        self.name = name
        self.parent = parent
        self.ledger = Ledger()

    def __eq__(self, value):
        return self.name == value.name if isinstance(value, Account) else False
    
    def __repr__(self):
        return f'{self.name}, {self.get_balance()}'

    def get_balance(self) -> int:
        return self.ledger.balance

class AccountManager:

    def __init__(self):
        self.journal = Journal()
        self.accounts:dict[int,Account] = {0: Account('root')}
        self.account_num = 1
        self._generate_parents()

    def _generate_parents(self):
        for name in PARENTS:
            self.add_account(name, 0)

    def add_transaction(self, date: datetime,
            description: str,
            credit_acct: int,
            debit_acct: int,
            amount:int) -> int:
        if credit_acct not in self.accounts:
            raise ValueError(f"No account {credit_acct}")
        if debit_acct not in self.accounts:
            raise ValueError(f"No account {debit_acct}")
        txn = JournalTransaction(date,
            description,
            credit_acct,
            debit_acct,
            amount
            )
        return self.journal.add_transaction(txn)

    def add_account(self, name: str, parent: int | None = None) -> None:
        if name in [a.name for a in self.accounts.values()]:
            raise ValueError(f'Account {name} already exists')
        self.accounts[self.account_num] = Account(name, parent)
        self.account_num += 1


        
    def generate_ledger(self):
        for acct in self.accounts.values():
            acct.ledger.clear_entries()
        for txn in self.journal.chronological():
            self.accounts[txn.debit_acct].ledger.add_entry(
                txn.date,
                txn.description,
                0,
                txn.amount
                
            )
            self.accounts[txn.credit_acct].ledger.add_entry(
                txn.date,
                txn.description,
                txn.amount,
                0
            )
        total = 0
        for account in self.accounts.values():
            total += account.get_balance()
        if total != 0:
            raise Exception(f'Trial Balance is {total}. Book is unbalanced')
    def build_tree(self):
        tree = {}
        for key, account in self.accounts.items():
            if account.parent is not None:
                if account.parent not in tree.keys():
                    tree[account.parent] = [key]
                else:
                    tree[account.parent].append(key)
        return tree
    def _print_tree(self, tree, node, dashes):
        for item in tree[node]:
            if tree.get(item, None) is not None:
                self._print_tree(tree, item, dashes+1)
            else:
                print('-'*dashes + str(self.accounts[item]))
    def print_tree(self):
        tree = self.build_tree()
        for item in tree[0]:
            print(self.accounts[item])
            if tree.get(item, None) is not None:
                self._print_tree(tree, item, 1)





    

    

