from ledger.models.accounts import AccountManager
from datetime import datetime

def main():
    acct_manager = AccountManager()
    acct_manager.add_account('test1',1)
    acct_manager.add_account('test2',2)
    acct_manager.add_account('test3',3)
    acct_manager.add_transaction(
        datetime.today(),
        "Test",
        6,
        7,
        100

    )
    acct_manager.generate_ledger()
    acct_manager.print_tree()
    

main()