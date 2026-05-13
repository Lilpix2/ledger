"""Tests for CSV import with account mapping dialog.

The import flow should:
1. Parse the CSV to detect all unique categories
2. Let the user map each category to a ledger account
3. Import transactions using the mapped accounts
"""

import tempfile, os, csv
from ledger.scripts.qif_to_csv import parse_qif
from ledger.controllers.accounts import AccountManager
from collections import Counter


SAMPLE_CSV = """Date,Amount,Payee,Memo,Category,Type,CheckNum,Cleared,Ticker
1/17'23,204.56,Opening Balance,,[Alex College XX3233],Bank,,X,
1/18'23,50.00,Luis Canales,,[Trust Checking 7290],Bank,,*,
1/20'23,-50.00,Online Transfer To HS,,[Alex HS Checking 8082],Bank,,*,
2/22'23,11.13,Venmo Cashout,,Kids:Income,Bank,,*,
2/24'23,-13.00,Venmo,,Kids:Income,Bank,,*,
8/26'24,249.91,Mathnasium Paycheck,,Kids:Income/Alex,Bank,,*,
3/21'23,-45.00,Discover Payment,,[Alex Discover XX5372],Bank,,*,
"""


# ── Detect unique categories from CSV ─────────────────────────────


def detect_categories(csv_text: str) -> dict[str, list[dict]]:
    """Scan CSV and return {category: [sample_rows]} with metadata."""
    reader = csv.DictReader(csv_text.splitlines())
    cats: dict[str, list[dict]] = {}
    for row in reader:
        cat = (row.get("Category") or "").strip()
        if cat:
            if cat not in cats:
                cats[cat] = []
            if len(cats[cat]) < 3:  # keep up to 3 samples
                cats[cat].append({
                    "date": row.get("Date", ""),
                    "amount": row.get("Amount", ""),
                    "payee": row.get("Payee", ""),
                })
    return cats


class TestDetectCategories:
    """Detecting unique categories from CSV content."""

    def test_detects_all_categories(self):
        cats = detect_categories(SAMPLE_CSV)
        expected = {"[Alex College XX3233]", "[Trust Checking 7290]",
                     "[Alex HS Checking 8082]", "Kids:Income",
                     "Kids:Income/Alex", "[Alex Discover XX5372]"}
        assert set(cats.keys()) == expected

    def test_bracket_accounts_detected(self):
        cats = detect_categories(SAMPLE_CSV)
        assert "[Alex College XX3233]" in cats
        assert "[Alex HS Checking 8082]" in cats

    def test_income_categories_detected(self):
        cats = detect_categories(SAMPLE_CSV)
        assert "Kids:Income" in cats
        assert "Kids:Income/Alex" in cats

    def test_empty_category_in_file(self):
        csv_text = """Date,Amount,Payee,Category\n1/17'23,10.00,Test,\n"""
        cats = detect_categories(csv_text)
        assert len(cats) == 0

    def test_sample_rows_with_each_category(self):
        cats = detect_categories(SAMPLE_CSV)
        for cat, samples in cats.items():
            assert len(samples) >= 1
            for s in samples:
                assert "date" in s
                assert "amount" in s
                assert "payee" in s


# ── Auto-suggest account type from category name ──────────────────


def suggest_account_type(cat: str) -> str:
    """Suggest an account type (ASSET, INCOME, EXPENSE) for a category.

    Rules:
      - Bracket categories [Account Name] → ASSET
      - Categories with "income" in the name → INCOME
      - Everything else → EXPENSE
    """
    if cat.startswith("["):
        return "ASSET"
    lower = cat.lower()
    if "income" in lower:
        return "INCOME"
    if "expense" in lower:
        return "EXPENSE"
    return "EXPENSE"


class TestSuggestAccountType:
    """Auto-detecting account type from category name."""

    def test_bracket_is_asset(self):
        assert suggest_account_type("[Alex College XX3233]") == "ASSET"
        assert suggest_account_type("[Trust Checking 7290]") == "ASSET"

    def test_income_is_income(self):
        assert suggest_account_type("Kids:Income") == "INCOME"
        assert suggest_account_type("Kids:Income/Alex") == "INCOME"

    def test_unknown_is_expense(self):
        assert suggest_account_type("Food") == "EXPENSE"
        assert suggest_account_type("Shopping") == "EXPENSE"

    def test_empty_returns_expense(self):
        assert suggest_account_type("") == "EXPENSE"
        assert suggest_account_type(":") == "EXPENSE"


# ── Full import with category mapping ─────────────────────────────


def import_csv_with_mapping(
    csv_text: str,
    db_path: str,
    account_name: str,
    cat_map: dict[str, int],
    dry_run: bool = False,
) -> int:
    """Import CSV rows using the provided category→account mapping.

    Args:
        csv_text: Raw CSV text.
        db_path: Database path.
        account_name: Name of the main asset account.
        cat_map: {category_string: account_id} mapping.
        dry_run: If True, count but don't write.

    Returns:
        Number of entries created.
    """
    from datetime import datetime
    from ledger.models.data_class import Split
    from ledger.controllers.accounts import AccountManager

    if dry_run:
        reader = csv.DictReader(csv_text.splitlines())
        return sum(1 for _ in reader)

    mgr = AccountManager(db_path)

    # Find or create the main account
    acct_id = None
    for aid, a in mgr.accounts.items():
        if a.name == account_name:
            acct_id = aid
            break
    if acct_id is None:
        acct_id = mgr.add_account(account_name, 1, "ASSET")

    reader = csv.DictReader(csv_text.splitlines())
    import_count = 0

    for row in reader:
        date_str = (row.get("Date") or "").strip()
        amt_str = (row.get("Amount") or "").strip()
        payee = (row.get("Payee") or "").strip()
        cat = (row.get("Category") or "").strip()

        if not date_str or not amt_str:
            continue

        try:
            dt = datetime.strptime(date_str, "%m/%d'%y")
        except ValueError:
            try:
                dt = datetime.strptime(date_str, "%m/%d/%Y")
            except ValueError:
                continue

        try:
            amt_cents = int(round(float(amt_str) * 100))
        except (ValueError, TypeError):
            continue

        if amt_cents == 0:
            continue

        target = cat_map.get(cat)
        if target is None:
            continue

        if amt_cents > 0:
            mgr.add_transaction(dt, payee or "Import",
                [Split(acct_id, amt_cents), Split(target, -amt_cents)])
        else:
            out = abs(amt_cents)
            mgr.add_transaction(dt, payee or "Import",
                [Split(target, out), Split(acct_id, -out)])
        import_count += 1

    mgr.generate_ledger()
    return import_count


class TestImportWithMapping:
    """Importing CSV rows using a category→account mapping."""

    def test_import_simple_mapping(self):
        import tempfile
        db_path = tempfile.mktemp(suffix=".db")
        try:
            mgr = AccountManager(db_path)
            # Create the accounts we'll map to
            college = mgr.add_account("Alex College XX3233", 1, "ASSET")
            income = mgr.add_account("Kids:Income", 4, "INCOME")
            mgr.db = None  # hack to close

            cat_map = {
                "[Alex College XX3233]": college,
                "[Trust Checking 7290]": income,
                "Kids:Income": income,
            }
            count = import_csv_with_mapping(SAMPLE_CSV, db_path, "College Check", cat_map)
            assert count >= 1
        finally:
            try: os.unlink(db_path)
            except: pass

    def test_import_keeps_balanced(self):
        import tempfile
        db_path = tempfile.mktemp(suffix=".db")
        try:
            mgr = AccountManager(db_path)
            college = mgr.add_account("Alex College XX3233", 1, "ASSET")
            income = mgr.add_account("Kids:Income", 4, "INCOME")
            hs_check = mgr.add_account("Alex HS Checking 8082", 1, "ASSET")
            trust = mgr.add_account("Trust Checking 7290", 1, "ASSET")
            discover = mgr.add_account("Alex Discover XX5372", 2, "LIABILITY")
            mgr.db = None

            cat_map = {
                "[Alex College XX3233]": college,
                "[Trust Checking 7290]": trust,
                "[Alex HS Checking 8082]": hs_check,
                "Kids:Income": income,
                "Kids:Income/Alex": income,
                "[Alex Discover XX5372]": discover,
            }
            import_csv_with_mapping(SAMPLE_CSV, db_path, "College Check", cat_map)
            mgr2 = AccountManager(db_path)
            eq = mgr2.check_accounting_equation()
            assert eq["balanced"], "Import should keep books balanced"
        finally:
            try: os.unlink(db_path)
            except: pass

    def test_dry_run_counts_rows(self):
        count = import_csv_with_mapping(SAMPLE_CSV, "/tmp/nonexistent.db", "Test", {}, dry_run=True)
        assert count == 7  # 7 data rows in sample

    def test_continue_without_mapping(self):
        """If no mapping is created, import produces 0 entries."""
        db_path = tempfile.mktemp(suffix=".db")
        try:
            count = import_csv_with_mapping(SAMPLE_CSV, db_path, "Test", {})
            assert count == 0
        finally:
            try: os.unlink(db_path)
            except: pass
