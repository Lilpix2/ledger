"""
Business logic: Account model and AccountManager.
"""

from __future__ import annotations

from datetime import datetime

from ..constants import PARENTS, ACCT_TYPE_MAP, ACCOUNT_SUBTYPES, DATE_STR
from ..database.database_controller import DatabaseController
from ..models.data_books import Ledger, Journal
from ..models.data_class import JournalTransaction, Split, Holding, Price

DEFAULT_DB_PATH = "data/journal.db"

# Account types and their normal balance direction.
# Debit-normal: ASSET, EXPENSE  (debits increase the balance)
# Credit-normal: LIABILITY, EQUITY, INCOME  (credits increase the balance)
DEBIT_NORMAL_TYPES = frozenset({"ASSET", "EXPENSE"})


class Account:
    def __init__(
        self,
        name: str,
        parent: int | None = None,
        acct_type: str = "ASSET",
        is_contra: bool = False,
        account_subtype: str | None = None,
    ):
        self.name = name
        self.parent = parent
        self.acct_type = acct_type
        self.is_contra = is_contra
        self.account_subtype = account_subtype
        self.ledger = Ledger()
        self.holdings: dict[str, Holding] = {}  # ticker → Holding

    def __eq__(self, value):
        return self.name == value.name if isinstance(value, Account) else False

    def __repr__(self):
        return f"{self.name}, {self.get_balance()}"

    def get_balance(self) -> int:
        return self.ledger.balance


class AccountManager:

    def __init__(self, db_path: str = DEFAULT_DB_PATH, db: DatabaseController | None = None):
        self.journal = Journal()
        self.accounts: dict[int, Account] = {0: Account("root")}
        self.db = db if db is not None else DatabaseController(db_path)
        self.db.ensure_tables()
        self._load_state()

    # ── Init / Load ─────────────────────────────────────────────────

    def _load_state(self):
        """Load accounts, holdings, and transactions from the database into memory."""
        db_accounts = self.db.load_accounts()

        if not db_accounts:
            self._generate_parents()
        else:
            for acct_id, name, parent_id, acct_type, is_contra, acc_subtype in db_accounts:
                parent = parent_id if parent_id is not None else 0
                self.accounts[acct_id] = Account(
                    name, parent, acct_type, bool(is_contra), acc_subtype
                )

            for txn in self.db.load_transactions():
                self.journal.add_transaction(txn)

            # Load holdings into each account
            for holding in self.db.load_holdings():
                if holding.account_id in self.accounts:
                    acct = self.accounts[holding.account_id]
                    acct.holdings[holding.ticker] = holding

        self.account_num = max(self.accounts.keys()) + 1
        self.generate_ledger()

    def _generate_parents(self):
        """Create the top-level parent accounts and default sub-accounts."""
        for name in PARENTS:
            acct_type = ACCT_TYPE_MAP.get(name, "ASSET")
            self.add_account(name, 0, acct_type)
        self.add_account('retained earnings', 3, ACCT_TYPE_MAP['equity'])
        self.add_account('cash', 1, ACCT_TYPE_MAP['assets'])
        self.add_account('accounts receivable', 1, ACCT_TYPE_MAP['assets'])
        self.add_account('dividends', 3, ACCT_TYPE_MAP['equity'], is_contra=True)
        self.add_account('accounts payable', 2, ACCT_TYPE_MAP['liabilities'])

    # ── Accounts ────────────────────────────────────────────────────

    def add_account(
        self,
        name: str,
        parent: int | None = None,
        acct_type: str | None = None,
        is_contra: bool = False,
        account_subtype: str | None = None,
    ) -> int:
        if not name or not name.strip():
            raise ValueError("Account name cannot be empty")
        name = name.strip()
        if parent is None:
            raise ValueError("Account parent is required")
        # Allow duplicate names under different parents (e.g. two mutual
        # funds with the same name in different brokerage accounts).
        if any(
            a.name == name and a.parent == parent
            for a in self.accounts.values()
        ):
            raise ValueError(f"Account '{name}' already exists under this parent")

        if account_subtype is not None and account_subtype not in ACCOUNT_SUBTYPES:
            raise ValueError(
                f"Invalid account_subtype '{account_subtype}'. "
                f"Valid: {', '.join(sorted(ACCOUNT_SUBTYPES))}"
            )

        # Inherit type from parent if not explicitly provided
        if acct_type is None and parent is not None and parent in self.accounts:
            acct_type = self.accounts[parent].acct_type
        elif acct_type is None:
            acct_type = "ASSET"

        db_parent = parent if parent != 0 else None
        acct_id = self.db.save_account(name, db_parent, acct_type, is_contra, account_subtype)
        self.accounts[acct_id] = Account(name, parent, acct_type, is_contra, account_subtype)
        return acct_id

    def update_account(
        self, acct_id: int, name: str,
        parent: int | None = None,
        acct_type: str | None = None,
        account_subtype: str | None = None,
    ) -> None:
        """Update an existing account's name, parent, type, or subtype."""
        if acct_id not in self.accounts:
            raise ValueError(f"Account #{acct_id} not found")
        acct = self.accounts[acct_id]
        acct.name = name
        if parent is not None:
            acct.parent = parent
        if acct_type is not None:
            acct.acct_type = acct_type
        if account_subtype is not None:
            acct.account_subtype = account_subtype
        db_parent = parent if parent is not None and parent != 0 else None
        # Don't overwrite DB fields that weren't explicitly changed
        final_type = acct_type if acct_type is not None else acct.acct_type
        final_subtype = account_subtype if account_subtype is not None else acct.account_subtype
        self.db.update_account(acct_id, name, db_parent, final_type, final_subtype)

    # ── Cycle detection ─────────────────────────────────────────

    @staticmethod
    def _is_descendant(
        acct_id: int, potential_ancestor_id: int, accounts: dict,
    ) -> bool:
        """Check if *acct_id* is a descendant of *potential_ancestor_id*."""
        while acct_id != 0:
            acct = accounts.get(acct_id)
            if acct is None:
                return False
            if acct.parent == potential_ancestor_id:
                return True
            if acct.parent is None:
                return False
            acct_id = acct.parent
        return False

    # ── Reassign children ───────────────────────────────────────

    def reassign_children(self, acct_id: int, target_parent_id: int) -> None:
        """Reparent all direct children of *acct_id* to *target_parent_id*."""
        if acct_id == 0:
            raise ValueError("Cannot reassign children of root account")
        if acct_id == target_parent_id:
            raise ValueError(
                f"Cannot reassign children to the same account ({acct_id})"
            )
        if target_parent_id not in self.accounts:
            raise ValueError(f"Target account {target_parent_id} not found")
        if self._is_descendant(target_parent_id, acct_id, self.accounts):
            raise ValueError(
                "Cannot reassign to a descendant (would create cycle)"
            )

        for child_id, acct in list(self.accounts.items()):
            if acct.parent == acct_id:
                acct.parent = target_parent_id
                self.db.update_account(
                    child_id, acct.name, target_parent_id,
                    acct.acct_type, acct.account_subtype,
                )
        self.db.reparent_children_in_db(acct_id, target_parent_id)

    # ── Reassign transactions ──────────────────────────────────

    def reassign_transactions(self, acct_id: int, target_acct_id: int) -> None:
        """Migrate all splits referencing *acct_id* to *target_acct_id*."""
        if acct_id == 0:
            raise ValueError("Cannot reassign transactions from root account")
        if acct_id == target_acct_id:
            raise ValueError(
                f"Cannot reassign to the same account ({acct_id})"
            )
        if target_acct_id not in self.accounts:
            raise ValueError(f"Target account {target_acct_id} not found")

        for txn in self.journal.transactions.values():
            for s in txn.splits:
                if s.account_id == acct_id:
                    s.account_id = target_acct_id
        self.db.reassign_splits_in_db(acct_id, target_acct_id)

    # ── Delete account (with options) ──────────────────────────

    def delete_account(self, acct_id: int) -> None:
        """Remove an account and cascade-delete its children and transactions.

        Does NOT check for children or referencing transactions — call
        ``reassign_children()`` / ``reassign_transactions()`` first if you
        want to migrate rather than cascade.
        """
        if acct_id == 0:
            raise ValueError("Cannot delete root account")

        # Cascade-delete children
        child_ids = [aid for aid, a in self.accounts.items() if a.parent == acct_id]
        for cid in child_ids:
            self.delete_account(cid)

        # Delete any transactions that reference this account
        txn_ids_to_delete = []
        for txn_id, txn in self.journal.transactions.items():
            for s in txn.splits:
                if s.account_id == acct_id:
                    txn_ids_to_delete.append(txn_id)
                    break
        for txn_id in txn_ids_to_delete:
            self.delete_transaction(txn_id)

        self.db._wipe_splits_for_account(acct_id)
        self.db.delete_account(acct_id)
        del self.accounts[acct_id]

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
        if not description or not description.strip():
            raise ValueError("Transaction description cannot be empty")
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
        db_id = self.db.save_transaction(date_str, description, splits)

        # ── In-memory ──
        txn = JournalTransaction(date, description, splits)
        return self.journal.add_transaction(txn, db_id=db_id)

    def delete_transaction(self, txn_id: int) -> None:
        """Remove a journal entry and regenerate all account balances."""
        # Look up the database journal_id before deleting from memory
        db_id = self.journal.get_db_id(txn_id)
        self.journal.delete_transaction(txn_id)
        if db_id is not None:
            self.db.delete_transaction(db_id)
        self.generate_ledger()

    # ── Ledger Generation ──────────────────────────────────────────

    def generate_ledger(self) -> None:
        """Recompute all account balances from the journal.

        Clears every account's ledger, then replays every transaction's
        splits in chronological order.
        """
        for acct in self.accounts.values():
            acct.ledger.clear_entries()

        for txn in self.journal.chronological():
            for s in txn.splits:
                acct = self.accounts.get(s.account_id)
                if acct is None:
                    continue  # stale split for deleted account — skip
                if s.amount > 0:
                    # Debit leg
                    acct.ledger.add_entry(
                        txn.date, txn.description, 0, s.amount,
                    )
                else:
                    # Credit leg (s.amount is negative)
                    acct.ledger.add_entry(
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
        """Walk up to find the top-level parent (direct child of root)."""
        if account_id == 0:
            return 0
        current = account_id
        while True:
            parent = self.accounts[current].parent
            if parent is None or parent == 0:
                return current
            current = parent

    def is_debit_normal(self, account_id: int) -> bool:
        """Return True if *account_id* is debit-normal.

        Contra accounts flip the normal balance of their type:
        a contra-asset is credit-normal even though its type is ASSET.
        """
        acct = self.accounts[account_id]
        normal = acct.acct_type in DEBIT_NORMAL_TYPES
        if acct.is_contra:
            return not normal
        return normal

    def get_display_balance(self, account_id: int) -> int:
        """Return the balance as a positive number in its **normal** direction.

        Debit-normal accounts (assets, expenses) display the raw balance
        directly.  Credit-normal accounts (liabilities, equity, income)
        have their sign flipped.  Contra accounts flip the rule.
        """
        raw = self.aggregated_balance(account_id)
        if self.is_debit_normal(account_id):
            return raw
        return -raw

    # ── Holdings / Positions ────────────────────────────────────────

    def set_holding(self, account_id: int, ticker: str, shares: float, cost_basis_cents: int) -> None:
        """Set a holding position for an account.

        Must be a subtype account (brokerage, mesp, retirement) -
        but enforcement is by convention, not restriction.
        """
        if account_id not in self.accounts:
            raise ValueError(f"No account with ID {account_id}")

        holding = Holding(account_id, ticker, shares, cost_basis_cents)
        self.db.save_holding(holding)
        self.accounts[account_id].holdings[ticker] = holding

    def get_holdings(self, account_id: int) -> list[Holding]:
        """Return all holdings for an account."""
        if account_id not in self.accounts:
            raise ValueError(f"No account with ID {account_id}")
        return list(self.accounts[account_id].holdings.values())

    def get_all_holdings(self) -> list[Holding]:
        """Return all holdings across all accounts."""
        result = []
        for acct_id, acct in self.accounts.items():
            if acct_id != 0 and acct.holdings:
                result.extend(acct.holdings.values())
        return result

    def delete_holding(self, account_id: int, ticker: str) -> None:
        """Remove a holding."""
        if account_id in self.accounts:
            self.accounts[account_id].holdings.pop(ticker, None)
        self.db.delete_holding(account_id, ticker)

    def get_holdings_nav(self, account_id: int) -> int:
        """Return the total cost basis of all holdings in an account (cents)."""
        acct = self.accounts.get(account_id)
        if not acct:
            return 0
        return sum(h.cost_basis_cents for h in acct.holdings.values())

    def save_price(self, ticker: str, date: str, price_cents: int) -> None:
        self.db.save_price(Price(ticker, date, price_cents))

    def get_price(self, ticker: str, date: str) -> int | None:
        """Get price for a ticker on a specific date."""
        prices = self.db.load_prices(ticker)
        for p in prices:
            if p.date == date:
                return p.price_cents
        return None

    def get_latest_price(self, ticker: str) -> int | None:
        """Get the most recent price quote for a ticker."""
        prices = self.db.load_prices(ticker)
        if not prices:
            return None
        return prices[-1].price_cents

    def portfolio_market_value(self, account_id: int) -> int | None:
        """Calculate the total market value of all holdings in an account.

        Returns None if any holding lacks a price quote.
        """
        acct = self.accounts.get(account_id)
        if not acct or not acct.holdings:
            return 0

        total = 0
        for h in acct.holdings.values():
            price = self.get_latest_price(h.ticker)
            if price is None:
                return None  # Can't calculate without prices
            total += int(h.shares * price)
        return total

    # ── Buy / Sell (Investment Transactions) ───────────────────────

    def _avg_cost_basis(self, account_id: int, ticker: str) -> float:
        """Return the average cost per share in cents for a holding."""
        acct = self.accounts.get(account_id)
        if not acct or ticker not in acct.holdings:
            return 0.0
        h = acct.holdings[ticker]
        if h.shares <= 0:
            return 0.0
        return h.cost_basis_cents / h.shares

    def buy_security(
        self,
        date: datetime,
        description: str,
        brokerage_id: int,
        cash_id: int,
        ticker: str,
        shares: float,
        price_cents: int,
        memo: str = "",
    ) -> int:
        """Buy shares of a security.

        Creates a journal entry debiting the brokerage (increasing asset
        value) and crediting the cash account (money leaving).  Updates
        the holdings table with the new position.

        Returns the journal entry ID.
        """
        if brokerage_id not in self.accounts or cash_id not in self.accounts:
            raise ValueError("Invalid account ID")
        if shares <= 0:
            raise ValueError("Shares must be positive")

        total_cents = int(shares * price_cents)
        if total_cents == 0:
            raise ValueError("Total cost must be non-zero")

        buy_memo = memo or f"Buy {shares} × {ticker} @ ${price_cents/100:.2f}"
        cash_memo = memo or f"Funds for {ticker} purchase"

        splits = [
            Split(brokerage_id, total_cents, memo=buy_memo),
            Split(cash_id, -total_cents, memo=cash_memo),
        ]
        txn_id = self.add_transaction(date, description, splits)

        # Update holdings (average cost basis)
        existing = self.accounts[brokerage_id].holdings.get(ticker)
        if existing:
            new_shares = existing.shares + shares
            new_cost = existing.cost_basis_cents + total_cents
        else:
            new_shares = shares
            new_cost = total_cents

        self.set_holding(brokerage_id, ticker, round(new_shares, 6), new_cost)
        return txn_id

    def sell_security(
        self,
        date: datetime,
        description: str,
        brokerage_id: int,
        cash_id: int,
        ticker: str,
        shares: float,
        price_cents: int,
        memo: str = "",
        gain_account_id: int | None = None,
    ) -> tuple[int, int]:
        """Sell shares of a security.

        Creates a journal entry:
        - Debit cash (proceeds arriving)
        - Credit brokerage (cost basis removed)
        - [Credit gain_account if realized gain, debit if realized loss]

        Uses average-cost-basis for the shares sold.

        Parameters
        ----------
        gain_account_id : int or None
            If provided, realized gains are booked to this account
            (credit for income, debit for loss/expense).  If None,
            gains/losses are not separately booked — they're implicit
            in the brokerage split.

        Returns
        -------
        tuple[int, int]
            (journal_entry_id, realized_gain_cents)
        """
        if brokerage_id not in self.accounts or cash_id not in self.accounts:
            raise ValueError("Invalid account ID")
        if shares <= 0:
            raise ValueError("Shares must be positive")

        existing = self.accounts[brokerage_id].holdings.get(ticker)
        if not existing:
            raise ValueError(f"No position in {ticker} to sell")
        if shares > existing.shares + 0.0001:
            raise ValueError(
                f"Cannot sell {shares} shares of {ticker}, "
                f"only {existing.shares:.4f} available"
            )

        total_cents = int(shares * price_cents)
        if total_cents == 0:
            raise ValueError("Total proceeds must be non-zero")

        # Average cost basis
        avg_cost = existing.cost_basis_cents / existing.shares
        cost_of_sold = int(round(shares * avg_cost))
        realized_gain = total_cents - cost_of_sold

        sell_memo = memo or f"Sell {shares} × {ticker} @ ${price_cents/100:.2f}"

        if gain_account_id is not None and realized_gain != 0:
            # Book realized gain/loss to a P&L account
            gain_memo = f"{'Gain' if realized_gain > 0 else 'Loss'} on {ticker} sale"
            splits = [
                Split(cash_id, total_cents, memo=sell_memo),
                Split(brokerage_id, -cost_of_sold, memo=f"Cost: {shares} × {ticker}"),
                Split(gain_account_id, -realized_gain, memo=gain_memo),
            ]
        else:
            # No separate gain tracking — fold proceeds into brokerage split
            splits = [
                Split(cash_id, total_cents, memo=sell_memo),
                Split(brokerage_id, -total_cents, memo=f"Sell {shares} × {ticker}"),
            ]

        txn_id = self.add_transaction(date, description, splits)

        # Update holdings
        new_shares = max(0.0, existing.shares - shares)
        new_cost = max(0, existing.cost_basis_cents - cost_of_sold)

        if new_shares < 0.0001:
            self.delete_holding(brokerage_id, ticker)
        else:
            self.set_holding(brokerage_id, ticker, round(new_shares, 6), new_cost)

        return txn_id, realized_gain

    # ── Financial Reports ───────────────────────────────────────────

    def check_accounting_equation(self) -> dict:
        """Return a snapshot of the accounting equation.

        Aggregates by `acct_type` (contra-aware raw balance summing).

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

        # Contra assets (credit-normal ASSETS) are already included in raw
        # They reduce a, which is correct for the equation

        net_income = i - ex
        # Dividends reduce retained earnings
        div = raw.get("DIVIDEND", 0)
        if div:
            # Dividends are stored as debit-normal (positive = paid)
            e -= div

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

    # ── Income Statement ────────────────────────────────────────────

    def gen_income_report(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Generate a structured income statement for a date period.

        Aggregates transactions by sub-account under income (ID 4) and
        expenses (ID 5), filtered by an optional date range.
        """
        income_ids = self.get_descendant_ids(4)
        expense_ids = self.get_descendant_ids(5)

        income_by_acct: dict[int, int] = {}
        expense_by_acct: dict[int, int] = {}

        # Without date filters: use direct account balances (not aggregated),
        # so parent accounts with direct income/expense splits are included
        # even if they have children — no double-counting since each account
        # tracks only its own splits.
        if not start_date and not end_date:
            for aid in sorted(income_ids):
                if aid in self.accounts:
                    raw = self.accounts[aid].get_balance()
                    if self.is_debit_normal(aid):
                        bal = raw
                    else:
                        bal = -raw
                    if bal != 0:
                        income_by_acct[aid] = bal
            for aid in sorted(expense_ids):
                if aid in self.accounts:
                    raw = self.accounts[aid].get_balance()
                    if self.is_debit_normal(aid):
                        bal = raw
                    else:
                        bal = -raw
                    if bal != 0:
                        expense_by_acct[aid] = bal
        else:
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

    # ── Retained Earnings Statement ─────────────────────────────────

    def gen_retained_earnings_statement(self) -> dict:
        """Build the Retained Earnings Statement.

        Structure: Beginning RE + Net Income − Dividends = Ending RE.

        Returns
        -------
        dict
            ``beginning_re``, ``net_income``, ``dividends``,
            ``ending_re`` — all in cents (display-normal).
        """
        re_id = 6
        re_bal_raw = self.accounts[re_id].get_balance()
        re_actual_display = -re_bal_raw  # RE is credit-normal

        ni = self.gen_income_report()["net_income"]

        # Dividends (contra-equity, debit-normal, raw = positive amount paid)
        div_ids = self.get_descendant_ids(9)
        div_total = 0
        for aid in div_ids:
            bal = self.accounts[aid].get_balance()
            if bal > 0:
                div_total += bal

        # If closing entries have been run, income/expense accounts are zeroed
        # and RE's ledger balance ALREADY contains this period's net income.
        # The income report still finds the original transactions, so we'd double-count.
        # Detect this case and zero out NI to avoid inflation.
        income_ids = self.get_descendant_ids(4)
        expense_ids = self.get_descendant_ids(5)
        all_zero = all(
            self.accounts[aid].get_balance() == 0
            for aid in list(income_ids) + list(expense_ids)
            if aid in self.accounts
        )
        if all_zero and ni != 0:
            ni = 0  # NI already closed into RE ledger balance

        # Prior period RE from ledger, current period from operations
        beginning_re = max(re_actual_display, 0)
        ending_re = beginning_re + ni - div_total

        return {
            "beginning_re": beginning_re,
            "net_income": ni,
            "dividends": div_total,
            "ending_re": ending_re,
        }

    def print_retained_earnings_statement(self) -> None:
        """Print a formatted Retained Earnings Statement."""
        r = self.gen_retained_earnings_statement()
        B = "═" * 46
        D = "─" * 46

        print()
        print(f"  {B}")
        print("  │      RETAINED EARNINGS STATEMENT      │")
        print(f"  {B}")
        print(f"  │   Retained Earnings, Beginning  ${r['beginning_re']/100:>8,.2f}")
        print(f"  │   + Net Income                  ${r['net_income']/100:>8,.2f}")
        print(f"  │   {D}")
        print(f"  │                                    ${(r['beginning_re']+r['net_income'])/100:>8,.2f}")
        if r['dividends']:
            print(f"  │   - Dividends                   ${r['dividends']/100:>8,.2f}")
            print(f"  │   {D}")
        print(f"  │   Retained Earnings, Ending    ${r['ending_re']/100:>8,.2f}")
        print(f"  {B}")

    # ── Balance Sheet ───────────────────────────────────────────────

    def gen_balance_sheet(self) -> dict:
        """Build a formal Balance Sheet (A = L + SE).

        Returns
        -------
        dict
            ``assets`` (list of (name, cents), sorted),
            ``total_assets`` (int),
            ``liabilities`` (list of (name, cents)),
            ``total_liabilities`` (int),
            ``equity`` (list of (name, cents)),
            ``total_equity`` (int),
            ``balanced`` (bool),
            ``total_liabilities_equity`` (int)
        """
        # NOTE: generate_ledger() assigns balances per account from
        # direct splits only — parents do NOT auto-sum children.
        # So showing ALL accounts with non-zero balance is correct
        # (no double-counting risk).
        asset_ids = self.get_descendant_ids(1)
        liability_ids = self.get_descendant_ids(2)
        equity_ids = self.get_descendant_ids(3)
        div_ids = self.get_descendant_ids(9)

        # Use the ACTUAL ledger Retained Earnings balance, not the computed
        # statement (which may double-count if closing entries were run twice).
        re_raw = self.accounts[6].get_balance()
        computed_re = max(-re_raw, 0)  # RE is credit-normal

        a_items: list[tuple[str, int]] = []
        l_items: list[tuple[str, int]] = []
        e_items: list[tuple[str, int]] = []

        # Assets: contra accounts subtract, normal add
        for aid in sorted(asset_ids):
            if aid in div_ids:
                continue
            raw = self.accounts[aid].get_balance()
            if raw == 0:
                continue
            acct = self.accounts[aid]
            # Display: positive in normal direction
            if self.is_debit_normal(aid):
                bal = raw
            else:
                bal = -raw
            # Contra assets reduce total; show with label
            if acct.is_contra:
                name = f"(-) {acct.name}"
                bal = -bal  # negate to show as subtraction
            else:
                name = acct.name
            a_items.append((name, bal))

        # Liabilities: credit-normal, flip raw
        for aid in sorted(liability_ids):
            raw = self.accounts[aid].get_balance()
            if raw == 0:
                continue
            acct = self.accounts[aid]
            bal = -raw
            l_items.append((acct.name, bal))

        # Equity: use computed Retained Earnings instead of ledger balance
        re_shown = False
        for aid in sorted(equity_ids):
            if aid == 6:
                if computed_re != 0:
                    e_items.append(("retained earnings", computed_re))
                    re_shown = True
                continue
            if aid in div_ids:
                continue  # skip dividends ledger balance
            raw = self.accounts[aid].get_balance()
            if raw == 0:
                continue
            acct = self.accounts[aid]
            if self.is_debit_normal(aid):
                bal = raw
            else:
                bal = -raw
            e_items.append((acct.name, bal))

        # Include net income in equity when income/expense haven't
        # been closed to RE yet, so A = L + E still holds for live data.
        # Detect closed state by checking if temp accounts are zeroed.
        ni_report = self.gen_income_report()
        ni = ni_report["net_income"]
        income_ids = self.get_descendant_ids(4)
        expense_ids = self.get_descendant_ids(5)
        all_zero = all(
            self.accounts[aid].get_balance() == 0
            for aid in list(income_ids) + list(expense_ids)
            if aid in self.accounts
        )
        if ni != 0 and not all_zero:
            e_items.append(("net income", ni))

        total_a = sum(b for _, b in a_items)
        total_l = sum(b for _, b in l_items)
        total_e = sum(b for _, b in e_items)

        return {
            "assets": a_items,
            "total_assets": total_a,
            "liabilities": l_items,
            "total_liabilities": total_l,
            "equity": e_items,
            "total_equity": total_e,
            "balanced": total_a == total_l + total_e,
            "total_liabilities_equity": total_l + total_e,
        }

    def print_balance_sheet(self) -> None:
        """Print a formatted Balance Sheet."""
        bs = self.gen_balance_sheet()
        B = "═" * 46
        D = "─" * 46

        print()
        print(f"  {B}")
        print("  │             BALANCE SHEET             │")
        print(f"  {B}")
        print()
        print("  │ ASSETS")
        print(f"  │ {D}")
        for name, bal in bs["assets"]:
            print(f"  │   {name:32s}  ${bal/100:>8,.2f}")
        print(f"  │ {D}")
        print(f"  │   {'Total Assets':32s}  ${bs['total_assets']/100:>8,.2f}")
        print()
        print("  │ LIABILITIES")
        print(f"  │ {D}")
        for name, bal in bs["liabilities"]:
            print(f"  │   {name:32s}  ${bal/100:>8,.2f}")
        print(f"  │ {D}")
        print(f"  │   {'Total Liabilities':32s}  ${bs['total_liabilities']/100:>8,.2f}")
        print()
        print("  │ EQUITY")
        print(f"  │ {D}")
        for name, bal in bs["equity"]:
            print(f"  │   {name:32s}  ${bal/100:>8,.2f}")
        print(f"  │ {D}")
        print(f"  │   {'Total Equity':32s}  ${bs['total_equity']/100:>8,.2f}")
        print(f"  │   {D}")
        te = bs["total_liabilities_equity"]
        print(f"  │   {'Total Liab. + Equity':32s}  ${te/100:>8,.2f}")
        status = "✓ A = L + E" if bs["balanced"] else "✗ UNBALANCED"
        print(f"  │   {status}")
        print(f"  {B}")

    # ── Account Summary ─────────────────────────────────────────────

    def gen_account_summary(self) -> dict:
        """Build a structured account summary grouped by type."""
        TYPES_IN_ORDER = ["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]
        TYPE_LABELS = {
            "ASSET": "Assets",
            "LIABILITY": "Liabilities",
            "EQUITY": "Equity",
            "INCOME": "Income",
            "EXPENSE": "Expenses",
        }

        by_type: dict[str, list[tuple[int, str, int]]] = {t: [] for t in TYPES_IN_ORDER}

        for aid, acct in self.accounts.items():
            if aid == 0:
                continue
            t = acct.acct_type
            raw = acct.get_balance()
            if self.is_debit_normal(aid):
                bal = raw
            else:
                bal = -raw
            by_type[t].append((aid, acct.name, bal))

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

        print()
        print(f"  │ {D}")
        print(f"  │   {'Net Worth':32s}  ${report['net_worth']/100:>8,.2f}")
        eq_status = "\u2713" if report["balanced"] else "\u2717 UNBALANCED"
        print(f"  │   {'Equation':32s}  {eq_status}")
        print(f"  {B}")

    # ── Closing Entries ─────────────────────────────────────────────

    def close_temps(self):
        """Close temporary accounts to Retained Earnings.

        Closes income, expenses, and dividends to Retained Earnings (ID 6).
        Call ``generate_ledger()`` afterwards.
        """
        expense_ids = self.get_descendant_ids(5)
        income_ids = self.get_descendant_ids(4)
        div_ids = self.get_descendant_ids(9)  # dividends under equity
        today = datetime.today()

        # Close each expense account (credit expense, debit RE)
        for aid in expense_ids:
            bal = self.accounts[aid].get_balance()
            if bal == 0:
                continue
            self.add_transaction(today, f'closing {self.accounts[aid].name}', [
                Split(aid, -bal),   # credit expense
                Split(6, bal),      # debit retained earnings
            ])

        # Close each income account (debit income, credit RE)
        for aid in income_ids:
            bal = self.accounts[aid].get_balance()
            if bal == 0:
                continue
            self.add_transaction(today, f'closing {self.accounts[aid].name}', [
                Split(aid, -bal),   # debit income
                Split(6, bal),      # credit retained earnings
            ])

        # Close dividends (credit dividends, debit RE)
        for aid in div_ids:
            bal = self.accounts[aid].get_balance()
            if bal == 0:
                continue
            # Dividends are debit-normal, positive = paid
            self.add_transaction(today, f'closing {self.accounts[aid].name}', [
                Split(aid, -bal),   # credit dividends (zero them)
                Split(6, bal),      # debit retained earnings
            ])
