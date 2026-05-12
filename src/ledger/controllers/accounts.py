"""
Business logic: Account model and AccountManager.
"""

from __future__ import annotations

from datetime import datetime

from ..constants import PARENTS, ACCT_TYPE_MAP, DATE_STR
from ..database.database_controller import DatabaseController
from ..models.data_books import Ledger, Journal
from ..models.data_class import JournalTransaction, Split

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

            for txn in self.db.load_transactions():
                self.journal.add_transaction(txn)

        self.account_num = max(self.accounts.keys()) + 1

    def _generate_parents(self):
        """Create the top-level parent accounts (assets, liabilities, etc.)."""
        for name in PARENTS:
            acct_type = ACCT_TYPE_MAP.get(name, "ASSET")
            self.add_account(name, 0, acct_type)
        self.add_account('retained earnings', 3, ACCT_TYPE_MAP['equity'])
        self.add_account('cash', 1, ACCT_TYPE_MAP['assets'])
        self.add_account('accounts receivable', 1, ACCT_TYPE_MAP['assets'])

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

    # ── Transactions (compound) ─────────────────────────────────────

    def add_transaction(
        self,
        date: datetime,
        description: str,
        splits: list[Split],
    ) -> int:
        """Add a compound journal entry with N splits.

        Parameters
        ----------
        date : datetime
        description : str
        splits : list of Split
            Each split: ``Split(account_id, amount, memo="")``.
            ``amount > 0`` = debit, ``amount < 0`` = credit.
            Sum of all amounts must equal 0.

        Returns
        -------
        int
            Transaction ID in the journal.
        """
        # ── Validation ──
        total = sum(s.amount for s in splits)
        if total != 0:
            raise ValueError(
                f"Unbalanced entry: sum of splits = {total} (must be 0)"
            )
        if not splits:
            raise ValueError("Entry must have at least one split")
        for s in splits:
            if s.account_id not in self.accounts:
                raise ValueError(f"No account with ID {s.account_id}")
            if s.amount == 0:
                raise ValueError("Split amount must be non-zero")

        # ── Persist ──
        date_str = date.strftime(DATE_STR)
        self.db.save_transaction(date_str, description, splits)

        # ── In-memory ──
        txn = JournalTransaction(date, description, splits)
        return self.journal.add_transaction(txn)

    # ── Ledger Generation ──────────────────────────────────────────

    def generate_ledger(self):
        """Recompute all account balances from the journal.

        Clears every account's ledger, then replays every transaction's
        splits in chronological order.
        """
        for acct in self.accounts.values():
            acct.ledger.clear_entries()

        for txn in self.journal.chronological():
            for s in txn.splits:
                if s.amount > 0:
                    # Debit leg
                    self.accounts[s.account_id].ledger.add_entry(
                        txn.date, txn.description, 0, s.amount,
                    )
                else:
                    # Credit leg (s.amount is negative)
                    self.accounts[s.account_id].ledger.add_entry(
                        txn.date, txn.description, -s.amount, 0,
                    )

        total = sum(a.get_balance() for a in self.accounts.values())
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

    def gen_income_report(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Generate a structured income statement for a date period.

        Aggregates transactions by sub-account under income (ID 4) and
        expenses (ID 5), filtered by an optional date range.

        Parameters
        ----------
        start_date, end_date: datetime or None

        Returns
        -------
        dict with keys: period, income, income_total, expenses,
                        expenses_total, net_income
        """
        income_ids = self.get_descendant_ids(4)
        expense_ids = self.get_descendant_ids(5)

        income_by_acct: dict[int, int] = {}
        expense_by_acct: dict[int, int] = {}

        for txn in self.journal.transactions.values():
            if start_date and txn.date < start_date:
                continue
            if end_date and txn.date > end_date:
                continue

            for s in txn.splits:
                # Credit legs (negative splits) on income accounts
                if s.amount < 0 and s.account_id in income_ids:
                    aid = s.account_id
                    income_by_acct[aid] = income_by_acct.get(aid, 0) + (-s.amount)
                # Debit legs (positive splits) on expense accounts
                if s.amount > 0 and s.account_id in expense_ids:
                    aid = s.account_id
                    expense_by_acct[aid] = expense_by_acct.get(aid, 0) + s.amount

        def _to_sorted(d: dict[int, int]) -> list[tuple[str, int]]:
            return sorted(
                [(self.accounts[aid].name, total) for aid, total in d.items()],
                key=lambda x: x[0],
            )

        income_list = _to_sorted(income_by_acct)
        expense_list = _to_sorted(expense_by_acct)

        income_total = sum(t for _, t in income_list)
        expense_total = sum(t for _, t in expense_list)

        return {
            "period": (start_date, end_date),
            "income": income_list,
            "income_total": income_total,
            "expenses": expense_list,
            "expenses_total": expense_total,
            "net_income": income_total - expense_total,
        }

    def print_income_report(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> None:
        """Print a formatted income statement to stdout."""
        report = self.gen_income_report(start_date, end_date)

        p_start, p_end = report["period"]
        if p_start or p_end:
            label_parts = []
            label_parts.append(p_start.strftime(DATE_STR) if p_start else "earliest")
            label_parts.append("to")
            label_parts.append(p_end.strftime(DATE_STR) if p_end else "now")
            period_str = " ".join(label_parts)
        else:
            period_str = "All Time"

        B = "═" * 46
        D = "─" * 46
        S = "─" * 38

        print()
        print(f"  {B}")
        print("  │           INCOME STATEMENT           │")
        print(f"  │  {period_str:42s}│")
        print(f"  {B}")
        print()
        print("  │ INCOME")
        print(f"  │ {D}")
        for name, total in report["income"]:
            print(f"  │   {name:32s}  ${total/100:>8,.2f}")
        print(f"  │ {S}")
        print(f"  │   {'Total Income':32s}  ${report['income_total']/100:>8,.2f}")
        print()
        print("  │ EXPENSES")
        print(f"  │ {D}")
        for name, total in report["expenses"]:
            print(f"  │   {name:32s}  ${total/100:>8,.2f}")
        print(f"  │ {S}")
        print(f"  │   {'Total Expenses':32s}  ${report['expenses_total']/100:>8,.2f}")
        net = report["net_income"]
        label = "Net Income" if net >= 0 else "Net Loss"
        print()
        print(f"  │ {D}")
        print(f"  │   {label:32s}  ${abs(net)/100:>8,.2f}")
        print(f"  {B}")

    # ── Closing Entries ─────────────────────────────────────────────

    def close_temps(self):
        """Close temporary accounts (income & expenses) to Retained Earnings.

        Creates one compound closing entry that zeroes all income and
        expense accounts, transferring their net balance to Retained
        Earnings (ID 6).  Call ``generate_ledger()`` afterwards.
        """
        expense_ids = self.get_descendant_ids(5)
        income_ids = self.get_descendant_ids(4)
        today = datetime.today()

        # Close each expense account (credit expense, debit RE)
        for aid in expense_ids:
            bal = self.accounts[aid].get_balance()
            if bal == 0:
                continue
            self.add_transaction(today, f'closing {self.accounts[aid].name}', [
                Split(aid, -bal),   # credit expense (to zero it)
                Split(6, bal),      # debit retained earnings
            ])

        # Close each income account (debit income, credit RE)
        for aid in income_ids:
            bal = self.accounts[aid].get_balance()
            if bal == 0:
                continue
            # bal is negative (credit-normal); flip sign for debits/credits
            self.add_transaction(today, f'closing {self.accounts[aid].name}', [
                Split(aid, -bal),   # debit income (to zero it; -negative = positive)
                Split(6, bal),      # credit retained earnings (bal is negative = credit)
            ])

    # ── Account Summary ────────────────────────────────────────────

    def gen_account_summary(self) -> dict:
        """Build a structured account summary grouped by type.

        Returns
        -------
        dict
            ``groups`` (list of dicts with keys: type_label, accounts,
                        total_cents),
            ``net_worth`` (int in cents),
            ``balanced`` (bool)
        """
        TYPES_IN_ORDER = ["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]
        TYPE_LABELS = {
            "ASSET": "Assets",
            "LIABILITY": "Liabilities",
            "EQUITY": "Equity",
            "INCOME": "Income",
            "EXPENSE": "Expenses",
        }

        # Collect accounts by type (skip root, skip parent categories that
        # have no balance of their own — they'll be shown via children)
        by_type: dict[str, list[tuple[int, str, int]]] = {t: [] for t in TYPES_IN_ORDER}

        for aid, acct in self.accounts.items():
            if aid == 0:
                continue
            t = acct.acct_type
            # Use raw balance, display-normalized (positive for everything)
            raw = acct.get_balance()
            if acct.acct_type in DEBIT_NORMAL_TYPES:
                bal = raw               # debit-normal: already positive
            else:
                bal = -raw              # credit-normal: flip sign
            by_type[t].append((aid, acct.name, bal))

        # Sort each group by name, build output
        groups = []
        for t in TYPES_IN_ORDER:
            entries = sorted(by_type[t], key=lambda x: x[1])
            total = sum(e[2] for e in entries)
            groups.append({
                "type_label": TYPE_LABELS.get(t, t),
                "accounts": entries,
                "total_cents": total,
            })

        eq = self.check_accounting_equation()

        return {
            "groups": groups,
            "net_worth": eq["net_worth"],
            "balanced": eq["balanced"],
        }

    def print_account_summary(self) -> None:
        """Print a formatted account summary to stdout."""
        report = self.gen_account_summary()

        B = "═" * 46
        D = "─" * 46
        S = "─" * 38

        print()
        print(f"  {B}")
        print("  │             ACCOUNT SUMMARY             │")
        print(f"  {B}")

        for group in report["groups"]:
            if not group["accounts"]:
                continue
            label = group["type_label"]
            print()
            print(f"  │ {label}")
            print(f"  │ {D}")
            for aid, name, bal in group["accounts"]:
                print(f"  │   {aid:3d}  {name:28s}  ${bal/100:>8,.2f}")
            print(f"  │ {S}")
            print(f"  │   {'Total ' + label:32s}  ${group['total_cents']/100:>8,.2f}")

        # Bottom line
        print()
        print(f"  │ {D}")
        print(f"  │   {'Net Worth':32s}  ${report['net_worth']/100:>8,.2f}")
        eq_status = "\u2713" if report["balanced"] else "\u2717 UNBALANCED"
        print(f"  │   {'Equation':32s}  {eq_status}")
        print(f"  {B}")
