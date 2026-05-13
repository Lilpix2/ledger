"""Tests for the Beancount import pipeline."""

import tempfile
import os
from datetime import datetime

import pytest

from ledger.scripts.import_beancount import (
    detect_subtype,
    beancount_type_to_ledger,
    _ensure_account_path,
)
from ledger.controllers.accounts import AccountManager


class TestSubtypeDetection:
    """Mapping Beancount account names to ledger subtypes."""

    @pytest.mark.parametrize("path,expected", [
        ("Assets:Checking:HS Checking", "checking"),
        ("Assets:Savings", "checking"),
        ("Assets:Checking:Main", "checking"),
        ("Assets:Brokerage:Schwab", "brokerage"),
        ("Assets:Schwab", "brokerage"),
        ("Assets:Fidelity:Brokerage", "brokerage"),
        ("Assets:MESP", "mesp"),
        ("Assets:MESP:MyPlan", "mesp"),
        ("Assets:Retirement:Roth IRA", "retirement"),
        ("Assets:Roth IRA", "retirement"),
        ("Assets:IRA:Traditional", "retirement"),
        ("Liabilities:Credit:Discover", "credit_card"),
        ("Liabilities:Discover:Credit", "credit_card"),
        ("Liabilities:Credit:Chase Sapphire", "credit_card"),
        ("Expenses:Food:Groceries", None),
        ("Income:Salary:W-2", None),
        ("Equity:Opening-Balances", None),
        ("Assets:House", None),
    ])
    def test_detect(self, path, expected):
        assert detect_subtype(path) == expected


class TestTypeMapping:
    """Beancount top-level type → ledger acct_type."""

    @pytest.mark.parametrize("path,expected", [
        ("Assets:Checking", "ASSET"),
        ("Liabilities:Credit", "LIABILITY"),
        ("Equity:Open", "EQUITY"),
        ("Income:Salary", "INCOME"),
        ("Expenses:Food", "EXPENSE"),
    ])
    def test_type(self, path, expected):
        assert beancount_type_to_ledger(path) == expected


class TestAccountPathBuilder:
    """Creating ledger accounts from Beancount paths."""

    def test_single_component(self, manager: AccountManager):
        """Full path that matches a top-level component."""
        aid = _ensure_account_path(manager, "Assets:Checking", "checking")
        assert aid > 0
        acct = manager.accounts[aid]
        assert acct.name == "Checking"
        assert acct.parent == 1  # Under Assets

    def test_nested_path(self, manager: AccountManager):
        """Three-component path creates intermediate accounts."""
        aid = _ensure_account_path(manager, "Assets:Checking:HS Checking", "checking")
        assert aid > 0
        acct = manager.accounts[aid]
        assert acct.name == "HS Checking"
        assert acct.account_subtype == "checking"

        # Intermediate "Checking" should exist
        checking_acct = manager.accounts[acct.parent]
        assert checking_acct.name == "Checking"
        assert checking_acct.account_subtype is None  # Not a leaf

    def test_path_under_liabilities(self, manager: AccountManager):
        """Credit card under Liabilities."""
        aid = _ensure_account_path(manager, "Liabilities:Credit:Discover", "credit_card")
        acct = manager.accounts[aid]
        assert acct.name == "Discover"
        assert acct.account_subtype == "credit_card"
        assert acct.acct_type == "LIABILITY"

    def test_idempotent(self, manager: AccountManager):
        """Creating the same path twice returns the same ID."""
        a1 = _ensure_account_path(manager, "Assets:Checking:Test")
        a2 = _ensure_account_path(manager, "Assets:Checking:Test")
        assert a1 == a2

    def test_unknown_top_level(self, manager: AccountManager):
        """Unknown top-level creates under root with inferred type."""
        aid = _ensure_account_path(manager, "Custom:Test")
        assert aid > 0
        assert manager.accounts[aid].acct_type == "ASSET"

    def test_subtype_on_leaf_only(self, manager: AccountManager):
        """Subtype is only applied to the leaf account, not intermediates."""
        aid = _ensure_account_path(manager, "Assets:Brokerage:Schwab:MyAccount", "brokerage")
        leaf = manager.accounts[aid]
        assert leaf.name == "MyAccount"
        assert leaf.account_subtype == "brokerage"

        # Intermediates should not have subtypes
        parent = manager.accounts[leaf.parent]
        assert parent.name == "Schwab"
        assert parent.account_subtype is None

        grandparent = manager.accounts[parent.parent]
        assert grandparent.name == "Brokerage"
        assert grandparent.account_subtype is None
