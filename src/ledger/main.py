"""Demo: creates a small account tree and posts transactions."""

from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


def main():
    manager = AccountManager()

    # Seed demo data on first run (no sub-accounts beyond defaults)
    if len(manager.accounts) <= 9:  # root + default children
        checking = manager.add_account("Checking", 1)   # under assets
        savings = manager.add_account("Savings", 1)     # under assets
        groceries = manager.add_account("Groceries", 5) # under expenses
        salary = manager.add_account("Salary", 4)       # under income

        # Payday: debit Checking (+), credit Salary (-)
        manager.add_transaction(
            datetime.today(),
            "Payday",
            [Split(salary, -200000), Split(checking, 200000)],
        )

        # Expense: debit Groceries (+), credit Checking (-)
        manager.add_transaction(
            datetime.today(),
            "Weekly shop",
            [Split(groceries, 4500), Split(checking, -4500)],
        )

        # Compound: split a paycheck across checking + savings
        manager.add_transaction(
            datetime.today(),
            "Split deposit",
            [Split(salary, -150000), Split(checking, 100000), Split(savings, 50000)],
        )

    manager.generate_ledger()
    manager.print_tree()
    manager.print_income_report()
    manager.print_account_summary()


main()
