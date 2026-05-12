from dataclasses import dataclass
from datetime import datetime
from ..constants import DATE_STR


@dataclass
class Split:
    """A single leg of a compound journal entry.

    Positive amount = debit, negative amount = credit.
    Sum of all splits in a JournalTransaction must always equal 0.
    """
    account_id: int
    amount: int
    memo: str = ""


@dataclass
class JournalTransaction:
    date: datetime
    description: str
    splits: list[Split]

    def total(self) -> int:
        """Total transaction value in cents (sum of all debits)."""
        return sum(s.amount for s in self.splits if s.amount > 0)

    def validate(self) -> bool:
        """Sum of all splits must equal 0 for double-entry integrity."""
        return sum(s.amount for s in self.splits) == 0

    def __dict__(self):
        return {
            'date': self.date.strftime(DATE_STR),
            'description': self.description,
            'splits': [(s.account_id, s.amount, s.memo) for s in self.splits],
        }


@dataclass
class LedgerEntry:
    date: datetime
    description: str
    credit: int
    debit: int
    balance: int

    def __dict__(self):
        return {
            'date': self.date.strftime(DATE_STR),
            'description': self.description,
            'credit': self.credit,
            'debit': self.debit,
            'balance': self.balance,
        }
