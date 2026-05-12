from dataclasses import dataclass
from datetime import datetime
from ..constants import DATE_STR


@dataclass
class JournalTransaction:
    date: datetime
    description: str
    credit_accts: tuple[dict]
    debit_accts: tuple[dict]
    amount: int

    def __dict__(self):
        output = {
            'date': self.date.strftime(DATE_STR),
            'description': self.description,
            'credit_acct': self.credit_accts,
            'debit_acct': self.debit_accts,
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
