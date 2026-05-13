"""
Core models for the double-entry accounting system.
Amounts are tracked in cents (int) to avoid floating-point issues.
"""

from datetime import datetime

from .data_class import JournalTransaction, LedgerEntry
from ..constants import DATE_STR

class Journal:
    """In-memory journal of transactions.

    Transactions are stored with auto-incrementing integer IDs internally.
    The database may use different IDs — ``db_id_map`` tracks the mapping
    so that ``delete_transaction(in_memory_id)`` can remove the right
    row from the database.
    """

    def __init__(self):
        self.transactions: dict[int, JournalTransaction] = {}
        self.sorted_ids: list[int] = []
        self.id_num = 0
        self.db_id_map: dict[int, int] = {}  # mem_id → db_id

    def add_transaction(self, txn: JournalTransaction, db_id: int | None = None) -> int:
        """Add a transaction and return its in-memory ID.

        If ``db_id`` is provided, the mapping is stored for later
        database-level operations (like delete).
        """
        mem_id = self.id_num
        self.transactions[mem_id] = txn
        self.sorted_ids.append(mem_id)
        self.id_num += 1
        if db_id is not None:
            self.db_id_map[mem_id] = db_id
        return mem_id

    def delete_transaction(self, txn_id: int) -> int:
        """Remove a journal entry by ID. Returns the removed ID."""
        if txn_id not in self.transactions:
            raise KeyError(f"Transaction {txn_id} not found")
        del self.transactions[txn_id]
        self.sorted_ids = [i for i in self.sorted_ids if i != txn_id]
        self.db_id_map.pop(txn_id, None)
        return txn_id

    def get_db_id(self, mem_id: int) -> int | None:
        """Return the database journal_id for an in-memory transaction ID."""
        return self.db_id_map.get(mem_id)

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
        self.entries = {}
        self.sorted_ids = []
        self.id_num = 0
        self.balance = 0
