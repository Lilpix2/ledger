"""Demo: creates a small account tree and runs the full accounting cycle."""

from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


def main():
    manager = AccountManager()

    # Seed demo data on first run
    if len(manager.accounts) <= 11:  # root + defaults + dividends + AP
        checking = manager.add_account("Checking", 1)
        savings = manager.add_account("Savings", 1)
        groceries = manager.add_account("Groceries", 5)
        salary = manager.add_account("Salary", 4)

        # Payday: debit Checking (+), credit Salary (-)
        manager.add_transaction(
            datetime.today(), "Payday",
            [Split(salary, -200000), Split(checking, 200000)],
        )

        # Expense: debit Groceries (+), credit Checking (-)
        manager.add_transaction(
            datetime.today(), "Weekly shop",
            [Split(groceries, 4500), Split(checking, -4500)],
        )

        # Compound: split a paycheck across checking + savings
        manager.add_transaction(
            datetime.today(), "Split deposit",
            [Split(salary, -150000), Split(checking, 100000), Split(savings, 50000)],
        )

    manager.generate_ledger()

    print("\n" + "=" * 50)
    print("  STEP 1: ACCOUNT TREE")
    print("=" * 50)
    manager.print_tree()

    print("\n" + "=" * 50)
    print("  STEP 2: INCOME STATEMENT")
    print("=" * 50)
    manager.print_income_report()

    print("\n" + "=" * 50)
    print("  STEP 3: RETAINED EARNINGS STATEMENT")
    print("=" * 50)
    manager.print_retained_earnings_statement()

    print("\n" + "=" * 50)
    print("  STEP 4: BALANCE SHEET")
    print("=" * 50)
    manager.print_balance_sheet()

    print("\n" + "=" * 50)
    print("  STEP 5: ACCOUNT SUMMARY (POST-CLOSE)")
    print("=" * 50)
    manager.close_temps()
    manager.generate_ledger()
    manager.print_account_summary()


main()
