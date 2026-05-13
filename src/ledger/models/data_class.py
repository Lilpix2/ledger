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


@dataclass
class Holding:
    """A security position within a brokerage/mesp/retirement account.

    ``account_id`` — the brokerage/mesp account owning the position.
    ``ticker`` — security symbol (e.g. AAPL, VTI, MESP-MD-R1).
    ``shares`` — number of shares held (REAL for fractional shares).
    ``cost_basis_cents`` — total cost basis in cents.
    """
    account_id: int
    ticker: str
    shares: float
    cost_basis_cents: int = 0


@dataclass
class Price:
    """A historical price quote for a security."""
    ticker: str
    date: str
    price_cents: int
