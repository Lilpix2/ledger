from .data_class import JournalTransaction, LedgerEntry
from ledger.constants import DATE_STR
from datetime import datetime
"""
Has the main models for my accounting system, It is a basic implementation of double book accounting,
Current design choices Include using the int type to track amounts in cents
"""

class Journal:
    def __init__(self):
        self.transactions: dict[int, JournalTransaction] = {}
        self.sorted_ids: list[int] = []
        self.id_num = 0

    def add_transaction(self, txn: JournalTransaction):
        self.transactions[self.id_num] = txn
        self.sorted_ids.append(self.id_num)
        self.id_num += 1
        return self.id_num - 1

    def chronological(self) -> list[JournalTransaction]:
        self.sorted_ids.sort(key=lambda i: self.transactions[i].date)
        return [self.transactions[i] for i in self.sorted_ids]

    def by_id(self, txn_id: int) -> JournalTransaction | None:
        return self.transactions.get(txn_id)
    
class Ledger:
    def __init__(self):
        self.entries: dict[int, LedgerEntry] = {}
        self.sorted_ids: list[int] = []
        self.id_num = 0
        self.balance = 0

    def __repr__(self):
        output = ""
        for entry in self.entries.values():
            string = f'{entry.date.strftime(DATE_STR)}, {entry.description}, {entry.credit}, {entry.debit}, {entry.balance}\n'
            output += string
        return output.strip()

    def add_entry(self,date: datetime, description: str, credit: int, debit: int):
        self.balance += debit
        self.balance -= credit
        txn = LedgerEntry(date,
            description,
            credit,
            debit,
            self.balance
        )
        self.entries[self.id_num] = txn
        self.sorted_ids.append(self.id_num)
        self.id_num += 1
        return self.id_num - 1

    def chronological(self) -> list[LedgerEntry]:
        self.sorted_ids.sort(key=lambda i: self.entries[i].date)
        return [self.entries[i] for i in self.sorted_ids]

    def by_id(self, txn_id: int) -> LedgerEntry | None:
        return self.entries.get(txn_id)
    
    def clear_entries(self):
        self.__init__()
