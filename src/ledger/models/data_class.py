from dataclasses import dataclass
from datetime import datetime


@dataclass
class JournalTransaction:
    date: datetime
    description: str
    credit_acct: int
    debit_acct: int
    amount: int


@dataclass
class LedgerEntry:
    date: datetime
    description: str
    credit: int
    debit: int
    balance: int
