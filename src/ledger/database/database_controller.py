import sqlite3

class DatabaseController:

    def __init__(self,db_str:str):
        self.db_str = db_str
    
    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_str)
    
    def load_state(self):
        with self.connnect() as conn:
            cur = conn.cursor()
            journal = cur.execute("SELECT * FROM journal;")
            accounts = cur.execute("SELECT * FROM acounts;")
            return accounts, journal
        
    def record_transaction(self, txn_dict: dict):
        with self.connnect() as conn:
            cur = conn.cursor()
            cur.execute("""
    INSERT INTO journal (date, description, credit_account_id, debit_account_id, amount)
    VALUES (?, ?, ?, ?, ?)
""", entry)