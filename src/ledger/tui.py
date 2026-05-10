from datetime import datetime
from ledger.constants import DATE_STR
from ledger.models.accounts import AccountManager
import os


def main_loop():
    manager = AccountManager()
    print("Welcome to ledger")
    while True:
        inp: str = input("""Options:
1: Add Account
2: Manage Journal
3: Print Account Summary
4: Exit
""")
        if not inp.isnumeric():
            print(f"Invalid input '{inp}', please input a number")
            continue

        inp = int(inp)
        if inp not in range(1, 5):
            print(f"Invalid option {inp}, please input 1-4")
            continue

        os.system("clear")

        if inp == 1:
            for acct_id, account in manager.accounts.items():
                if acct_id != 0:
                    print(f"{acct_id}: {account}")
            parent_input = input("Choose parent: ")
            name = input("Choose name: ")
            if not parent_input.isnumeric():
                print("Parent must be a number")
                continue
            parent_id = int(parent_input)
            if parent_id not in manager.accounts:
                print(f"{parent_id} is not a valid account number")
                continue
            manager.add_account(name, parent_id)

        elif inp == 2:
            for acct_id, account in manager.accounts.items():
                if acct_id != 0:
                    print(f"{acct_id}: {account}")
            date_str = input("Input date MM-DD-YYYY H:M:S: ")
            description = input("Enter description: ")
            debit = input("Choose account to debit: ")
            credit = input("Choose account to credit: ")
            amount = input("What is the amount: ")

            if not (debit.isnumeric() and credit.isnumeric() and amount.isnumeric()):
                print("Please make sure all inputs are valid numbers")
                continue

            try:
                date = datetime.strptime(date_str.strip(), DATE_STR)
                manager.add_transaction(
                    date,
                    description,
                    int(credit),
                    int(debit),
                    int(amount),
                )
                print("Successfully added a transaction")
            except Exception as e:
                print(f"Error parsing date: {e}")

        elif inp == 3:
            manager.generate_ledger()
            manager.print_tree()

        elif inp == 4:
            break


main_loop()
