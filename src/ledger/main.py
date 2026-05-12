"""Demo: creates a small account tree and posts a transaction."""

from datetime import datetime

from ledger.controllers.accounts import AccountManager


def main():
    manager = AccountManager()

    # Only seed demo data on first run (empty database)
    if len(manager.accounts) <= 6:  # root + 5 parents, no children yet
        checking = manager.add_account("Checking", 1)   # under assets
        savings = manager.add_account("Savings", 1)     # under assets
        groceries = manager.add_account("Groceries", 5) # under expenses
        salary = manager.add_account("Salary", 4)       # under income

        manager.add_transaction(datetime.today(), "Payday", salary, checking, 200000)
        manager.add_transaction(datetime.today(), "Weekly shop", groceries, checking, 4500)

    manager.generate_ledger()
    manager.print_tree()
    manager.print_income_report()


main()
