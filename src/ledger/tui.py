from models.accounts import AccountManager
from datetime import datetime
from constants import DATE_STR
import os
valid_inputs = [1,2,3,4]
def main_loop():
    manager = AccountManager()
    print('Welcome to ledger')
    while True:
        inp: str = input('''Options:
1: Add Account
2: Manage Journal
3: Print Account Summary
4: Exit
''')
        if inp.isnumeric():
            inp = int(inp)
            if inp in valid_inputs:
                os.system('clear')
                if inp == 1:
                    for account in manager.accounts:
                        if account != 0:
                            print(f'{account}: {manager.accounts[account]}')
                    account = input("Choose parent: ")
                    name = input('Choose name: ')
                    if account.isnumeric():
                        account = int(account)
                        if account in manager.accounts.keys():
                            manager.add_account(name, account)
                        else:
                            print(f'{account} is not a valid account number')
                    else:
                        print(f'{account} is not a number, please input a valid number')

                    
                elif inp == 2:
                    for account in manager.accounts:
                        if account != 0:
                            print(f'{account}: {manager.accounts[account]}')
                    date_str = input("Input date MM-DD-YYYY H:M:S")
                    description = input('Enter description: ')
                    debit = input('Choose account to debit: ')
                    credit = input('Choose account to credit: ')
                    amount = input('What is the amount: ')
                    try:
                        date = datetime.strptime(date_str.strip(), DATE_STR)
                        if debit.isnumeric() and credit.isnumeric() and amount.isnumeric():
                            manager.add_transaction(
                                date,
                                description,
                                int(credit),
                                int(debit),
                                int(amount)
                            )
                            print('Sucessfully added a transaction')
                        else:
                            print('Please make sure all inputs are valid numbers')


                    except Exception as e:
                        print(f'Error parsing input {e}')

                elif inp == 3:
                    manager.generate_ledger()
                    manager.print_tree()
                elif inp == 4:
                    break
        else:
            print('Invalid input {inp}, please input a number')

main_loop()
        