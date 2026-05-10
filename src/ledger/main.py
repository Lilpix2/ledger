"""Demo: creates a small account tree and posts a transaction."""

from datetime import datetime

from ledger.models.accounts import AccountManager


def main():
    manager = AccountManager()

    # Top-level parents are auto-created (assets, liabilities, etc.)
    # Add sub-accounts under them
    checking = manager.add_account("Checking", 1)   # under assets
    savings = manager.add_account("Savings", 1)     # under assets
    groceries = manager.add_account("Groceries", 5) # under expenses
    salary = manager.add_account("Salary", 4)       # under income

    # Transfer money from Salary → Checking
    manager.add_transaction(datetime.today(), "Payday", salary, checking, 200000)

    # Spend from Checking → Groceries
    manager.add_transaction(datetime.today(), "Weekly shop", groceries, checking, 4500)

    manager.generate_ledger()
    manager.print_tree()


main()
