"""Component tests for PortfolioTableModel.

Tests edge cases around holdings with/without price data,
empty portfolios, and non-brokerage account filtering.
"""
from __future__ import annotations

import tempfile

import pytest

from ledger.models.data_class import Holding, Price
from ledger.controllers.accounts import AccountManager


def _setup_portfolio_db(holdings: list[Holding],
                         prices: list[Price] | None = None) -> AccountManager:
    """Create a real temp DB with accounts, holdings, and optional prices."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    manager = AccountManager(f.name)
    # Add a brokerage account (parent = 0, root)
    broker_id = manager.add_account("Brokerage", 0, "ASSET", account_subtype="brokerage")
    # Add a non-brokerage asset (should be filtered out)
    manager.add_account("Checking", 0, "ASSET", account_subtype="checking")
    for h in holdings:
        h.account_id = broker_id
    # Inject holdings
    manager.accounts[broker_id].holdings = {h.ticker: h for h in holdings}
    for h in holdings:
        manager.db.save_holding(h)
    if prices:
        manager.db.bulk_save_prices([(p.ticker, p.date, p.price_cents) for p in prices])
    return manager


class TestPortfolioTableModel:
    """PortfolioTableModel edge case coverage."""

    def test_emptyPortfolio_zeroRows(self, qt_app):
        """No holdings → zero rows in the model."""
        from ledger.gui_pyside.gui_app_pyside import PortfolioTableModel
        manager = _setup_portfolio_db([])
        model = PortfolioTableModel(manager)
        assert model.rowCount() == 0

    def test_holdingsWithPrices_populatesRows(self, qt_app):
        """Holdings with price data appear as rows."""
        from ledger.gui_pyside.gui_app_pyside import PortfolioTableModel
        holdings = [
            Holding(0, "VTI", 10.0, 250000),
            Holding(0, "BND", 5.0, 50000),
        ]
        prices = [
            Price("VTI", "latest", 26000),   # $260/share → mkt_val = 10 * 26000 = 260000
            Price("BND", "latest", 11000),   # $110/share → mkt_val = 5 * 11000 = 55000
        ]
        manager = _setup_portfolio_db(holdings, prices)
        model = PortfolioTableModel(manager)
        assert model.rowCount() == 2

    def test_holdingWithoutPrice_skipped(self, qt_app):
        """Holding with no price record is silently skipped (no crash)."""
        from ledger.gui_pyside.gui_app_pyside import PortfolioTableModel
        holdings = [
            Holding(0, "VTI", 10.0, 250000),      # has price
            Holding(0, "UNKNOWN", 1.0, 5000),      # no price → should be skipped
        ]
        prices = [
            Price("VTI", "latest", 26000),
        ]
        manager = _setup_portfolio_db(holdings, prices)
        model = PortfolioTableModel(manager)
        assert model.rowCount() == 1

    def test_allHoldingsWithoutPrice_zeroRows(self, qt_app):
        """All holdings lack price data → empty model (no crash)."""
        from ledger.gui_pyside.gui_app_pyside import PortfolioTableModel
        holdings = [
            Holding(0, "UNKNOWN1", 10.0, 10000),
            Holding(0, "UNKNOWN2", 5.0, 5000),
        ]
        manager = _setup_portfolio_db(holdings, prices=None)
        model = PortfolioTableModel(manager)
        assert model.rowCount() == 0

    def test_nonBrokerageAccountsIgnored(self, qt_app):
        """Holdings under non-brokerage accounts are not shown."""
        from ledger.gui_pyside.gui_app_pyside import PortfolioTableModel
        manager = _setup_portfolio_db([])
        # Add holding directly to Checking (non-brokerage)
        checking_id = 2  # second account added in _setup_portfolio_db
        h = Holding(checking_id, "VTI", 10.0, 250000)
        manager.accounts[checking_id].holdings["VTI"] = h
        manager.db.save_holding(h)
        manager.db.save_price(Price("VTI", "latest", 26000))
        model = PortfolioTableModel(manager)
        assert model.rowCount() == 0

    def test_data_format_cents_forIntColumns(self, qt_app):
        """Int columns (cost, price, mkt_val, pnl) format as currency strings."""
        from ledger.gui_pyside.gui_app_pyside import PortfolioTableModel
        holdings = [Holding(0, "VTI", 10.0, 250000)]
        prices = [Price("VTI", "latest", 26000)]
        manager = _setup_portfolio_db(holdings, prices)
        model = PortfolioTableModel(manager)
        # Cost column (index 3) — 250000 cents → "$2,500.00"
        cost_display = model.data(model.index(0, 3))
        assert cost_display == "$2,500.00"
        # Price column (index 4) — 26000 cents → "$260.00"
        price_display = model.data(model.index(0, 4))
        assert price_display == "$260.00"
