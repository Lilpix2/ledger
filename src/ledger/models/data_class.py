from dataclasses import dataclass
from datetime import datetime
from ..constants import DATE_STR


@dataclass
class JournalTransaction:
    date: datetime
    description: str
    credit_acct: int
    debit_acct: int
    amount: int

    def __dict__(self):
        output = {
            'date': self.date.strftime(DATE_STR),
            'description': self.description,
            'credit_acct': self.credit_acct,
            'debit_acct': self.debit_acct,
            'amount': self.amount
        }
        return output


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
