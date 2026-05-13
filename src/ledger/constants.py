DATE_STR = '%m-%d-%Y %H:%M:%S'
PARENTS = ['assets', 'liabilities', 'equity', 'income', 'expenses']

# Account type for each top-level parent.
ACCT_TYPE_MAP = {
    'assets': 'ASSET',
    'liabilities': 'LIABILITY',
    'equity': 'EQUITY',
    'income': 'INCOME',
    'expenses': 'EXPENSE',
}

# Account subtypes for classification beyond accounting type.
# Used by checking, credit cards, brokerage, MESPs, and retirement accounts.
ACCOUNT_SUBTYPES = frozenset({
    "checking",
    "credit_card",
    "brokerage",
    "mesp",
    "retirement",
})