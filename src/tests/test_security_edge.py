"""Comprehensive edge-case tests for security buy/sell/portfolio operations.

This file covers the boundary value analysis, equivalence partitioning, and
null/error paths for:

    - buy_security       (M=11 cyclomatic)
    - sell_security      (M=16 cyclomatic)
    - _avg_cost_basis    (M=4  cyclomatic)
    - portfolio_market_value (M=5 cyclomatic)

All tests use the ``fast_manager`` fixture (MockDB, zero disk I/O).
Follows strict AAA pattern (Arrange, Act, Assert).
"""

import pytest
from datetime import datetime

from ledger.controllers.accounts import AccountManager
from ledger.models.data_class import Split


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _fund_and_buy(
    mgr: AccountManager,
    ticker: str = "VTI",
    shares: float = 10,
    price_cents: int = 27500,
    brokerage_subtype: str = "brokerage",
) -> tuple[int, int]:
    """Create funded checking + brokerage, then buy *ticker*.

    Returns (checking_id, brokerage_id).
    """
    checking = mgr.add_account("Checking", 1)
    brokerage = mgr.add_account("Brokerage", 1, account_subtype=brokerage_subtype)
    mgr.add_transaction(
        datetime(2026, 1, 1), "Fund",
        [Split(brokerage, 500000), Split(checking, 500000),
         Split(6, -1000000)],
    )
    mgr.buy_security(
        datetime(2026, 2, 1), f"Buy {ticker}",
        brokerage, checking, ticker, shares, price_cents,
    )
    return checking, brokerage


# ═══════════════════════════════════════════════════════════════════
# BuySecurity — Exhaustive Edge Cases (M=11 + BVA + error ≈ 20 tests)
# ═══════════════════════════════════════════════════════════════════

class TestBuySecurityEdge:
    """Exhaustive buy-security edge cases: BVA, EP, null/error paths."""

    # ── Zero / Negative shares ────────────────────────────────────

    def test_buySecurity_zeroShares_raises(self, fast_manager: AccountManager) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Zero", brokerage, checking, "VTI", 0, 10000,
            )

    def test_buySecurity_negativeShares_raises(self, fast_manager: AccountManager) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Neg", brokerage, checking, "VTI", -5, 10000,
            )

    # ── Fractional shares ─────────────────────────────────────────

    def test_buySecurity_fractionalShares_preservesPrecision(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 200000), Split(brokerage, 200000), Split(6, -400000)],
        )
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Fractional",
            brokerage, checking, "VTI", 10.54321, 10500,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        # 10.54321 × 10500 = 110703.705 — int() floors to 110703
        assert abs(h.shares - 10.54321) < 1e-6
        assert h.cost_basis_cents == int(10.54321 * 10500)

    def test_buySecurity_tinyFraction_rounding(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 100000), Split(brokerage, 100000), Split(6, -200000)],
        )
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Tiny",
            brokerage, checking, "AAPL", 0.001, 1500000,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 0.001) < 1e-6
        # 0.001 × 1500000 = 1500 — small but non-zero
        assert h.cost_basis_cents == 1500

    # ── Zero-cost / zero-value ────────────────────────────────────

    def test_buySecurity_zeroPriceCents_raises(self, fast_manager: AccountManager) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)
        with pytest.raises((ValueError, ZeroDivisionError)):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Free", brokerage, checking, "VTI", 10, 0,
            )

    # ── Invalid account IDs ───────────────────────────────────────

    def test_buySecurity_invalidBrokerageAccount_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Bad", 99999, checking, "VTI", 10, 10000,
            )

    def test_buySecurity_invalidCashAccount_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.buy_security(
                datetime(2026, 1, 1), "Bad", brokerage, 99999, "VTI", 10, 10000,
            )

    # ── Same account for brokerage and cash ───────────────────────

    def test_buySecurity_sameAccount_brokerageAndCash_booksEntry(
        self, fast_manager: AccountManager,
    ) -> None:
        """Both IDs are the same account — the journal creates a balanced entry
        with opposing splits on the same account.  This is technically valid
        double-entry (net zero on the account) and should produce a holding."""
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 500000), Split(6, -500000)],
        )
        # Both brokerage_id and cash_id are the same — net effect is a round-trip
        fast_manager.buy_security(
            datetime(2026, 1, 1), "Self", brokerage, brokerage, "VTI", 10, 10000,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 10.0
        assert h.cost_basis_cents == 100000

    # ── Two buys of same ticker (average cost) ────────────────────

    def test_buySecurity_twoBuysSameTicker_accumulatesShares(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 2000000), Split(brokerage, 1000000), Split(6, -3000000)],
        )
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Batch1", brokerage, checking, "VTI", 10, 27500,
        )
        fast_manager.buy_security(
            datetime(2026, 3, 1), "Batch2", brokerage, checking, "VTI", 5, 28000,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 15.0
        assert h.cost_basis_cents == 275000 + 140000

    def test_buySecurity_threeBuys_roundingTolerance(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 5000000), Split(brokerage, 5000000), Split(6, -10000000)],
        )
        fast_manager.buy_security(datetime(2026, 1, 1), "B1",
                                  brokerage, checking, "VTI", 10, 10000)
        fast_manager.buy_security(datetime(2026, 2, 1), "B2",
                                  brokerage, checking, "VTI", 20, 11000)
        fast_manager.buy_security(datetime(2026, 3, 1), "B3",
                                  brokerage, checking, "VTI", 15, 10500)
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 45.0
        expected_cost = 10 * 10000 + 20 * 11000 + 15 * 10500
        assert h.cost_basis_cents == expected_cost

    # ── Buy with no money (insufficient cash) ─────────────────────

    def test_buySecurity_insufficientCash_accountStillRecords(
        self, fast_manager: AccountManager,
    ) -> None:
        """The code doesn't check available cash — it just records the
        transaction.  This means the brokerage gets the asset but the cash
        account goes negative.  Verify the trades still go through."""
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # Only $1000 in checking but trying to buy $275k — brokerage has no funds
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 1000), Split(6, -1000)],
        )
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Overdraft",
            brokerage, checking, "VTI", 10, 27500,
        )
        fast_manager.generate_ledger()
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 10.0
        assert h.cost_basis_cents == 275000
        # Cash account goes negative (overdraft) — allowed by the model
        assert fast_manager.get_display_balance(checking) < 0

    # ── Buy large number of shares (overflow-like / rounding) ─────

    def test_buySecurity_largeShares_roundingSafe(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 100000000), Split(brokerage, 100000000),
             Split(6, -200000000)],
        )
        large_shares = 999999.999999
        fast_manager.buy_security(
            datetime(2026, 2, 1), "Large",
            brokerage, checking, "VTI", large_shares, 100,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        assert abs(h.shares - round(large_shares, 6)) < 1e-6
        assert h.cost_basis_cents == int(large_shares * 100)

    # ── Multiple different tickers in same account ────────────────

    def test_buySecurity_multipleTickers_sameAccount(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(brokerage, 5000000), Split(6, -15000000)],
        )
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy VTI",
                                  brokerage, checking, "VTI", 100, 27500)
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy AAPL",
                                  brokerage, checking, "AAPL", 50, 15000)
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy BND",
                                  brokerage, checking, "BND", 200, 7500)
        holdings = fast_manager.get_holdings(brokerage)
        assert len(holdings) == 3
        tickers = {h.ticker for h in holdings}
        assert tickers == {"VTI", "AAPL", "BND"}

    # ── Buy on different account subtypes ─────────────────────────

    def test_buySecurity_buysInMespAccount_createsHolding(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        mesp = fast_manager.add_account("MESP", 1, account_subtype="mesp")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 5000000), Split(mesp, 5000000), Split(6, -10000000)],
        )
        fast_manager.buy_security(
            datetime(2026, 2, 1), "MESP Buy", mesp, checking, "MESP-MD-R1", 50, 10750,
        )
        h = fast_manager.get_holdings(mesp)[0]
        assert h.shares == 50.0
        assert h.cost_basis_cents == 50 * 10750

    def test_buySecurity_buysInRetirementAccount_createsHolding(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        ira = fast_manager.add_account("Roth IRA", 1, account_subtype="retirement")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 5000000), Split(ira, 5000000), Split(6, -10000000)],
        )
        fast_manager.buy_security(
            datetime(2026, 2, 1), "IRA Buy", ira, checking, "VT", 200, 10500,
        )
        h = fast_manager.get_holdings(ira)[0]
        assert h.shares == 200.0


# ═══════════════════════════════════════════════════════════════════
# SellSecurity — Exhaustive Edge Cases (M=16 + BVA + null/error ≈ 30 tests)
# ═══════════════════════════════════════════════════════════════════

class TestSellSecurityEdge:
    """Exhaustive sell-security edge cases."""

    # ── Partial sale ──────────────────────────────────────────────

    def test_sellSecurity_partial_reducesCorrectly(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell Partial",
            brokerage, checking, "VTI", 4, 29500,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 6.0) < 0.001
        # Cost basis reduced proportionally: 4/10 × 275000 = 110000 removed
        assert h.cost_basis_cents == 275000 - 110000

    def test_sellSecurity_partialFractional_shares(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10.543, 10500)
        fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell Partial Fractional",
            brokerage, checking, "VTI", 3.1415, 11000,
        )
        h = fast_manager.get_holdings(brokerage)[0]
        remaining = round(10.543 - 3.1415, 6)
        assert abs(h.shares - remaining) < 0.001

    # ── Full exit ─────────────────────────────────────────────────

    def test_sellSecurity_fullExit_removesHolding(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell All",
            brokerage, checking, "VTI", 10, 29500,
        )
        assert len(fast_manager.get_holdings(brokerage)) == 0

    def test_sellSecurity_fullExitRemoves_equationBalanced(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        gain = fast_manager.add_account("Cap Gains", 4)
        fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell All",
            brokerage, checking, "VTI", 10, 29500,
            gain_account_id=gain,
        )
        fast_manager.generate_ledger()
        eq = fast_manager.check_accounting_equation()
        assert eq["balanced"] is True, f"Equation: A={eq['assets']} L={eq['liabilities']} E={eq['equity']}+NI={eq['net_income']}"

    # ── Sell more than owned ──────────────────────────────────────

    def test_sellSecurity_excessShares_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 5, 27500)
        with pytest.raises(ValueError, match="Cannot sell|only"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Excess",
                brokerage, checking, "VTI", 10, 29500,
            )

    def test_sellSecurity_excessByFraction_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        # Exceed by just 0.0001 — boundary above
        with pytest.raises(ValueError, match="Cannot sell|only"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Excess Tiny",
                brokerage, checking, "VTI", 10.0002, 29500,
            )

    def test_sellSecurity_exactBoundary_works(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        # Sell exactly 10 — boundary at the limit
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell All",
            brokerage, checking, "VTI", 10, 29500,
        )
        assert len(fast_manager.get_holdings(brokerage)) == 0

    # ── No position ───────────────────────────────────────────────

    def test_sellSecurity_noPosition_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1)
        with pytest.raises(ValueError, match="No position"):
            fast_manager.sell_security(
                datetime(2026, 1, 1), "No Pos",
                brokerage, checking, "VTI", 5, 10000,
            )

    def test_sellSecurity_wrongTicker_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        with pytest.raises(ValueError, match="No position"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Wrong",
                brokerage, checking, "AAPL", 5, 29500,
            )

    # ── Zero / Negative shares ────────────────────────────────────

    def test_sellSecurity_zeroShares_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Zero",
                brokerage, checking, "VTI", 0, 29500,
            )

    def test_sellSecurity_negativeShares_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        with pytest.raises(ValueError, match="Shares must be positive"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Neg",
                brokerage, checking, "VTI", -5, 29500,
            )

    # ── Invalid accounts ──────────────────────────────────────────

    def test_sellSecurity_invalidBrokerage_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.sell_security(
                datetime(2026, 1, 1), "Bad",
                99999, checking, "VTI", 5, 10000,
            )

    def test_sellSecurity_invalidCashAccount_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        with pytest.raises(ValueError, match="Invalid account"):
            fast_manager.sell_security(
                datetime(2026, 1, 1), "Bad",
                brokerage, 99999, "VTI", 5, 10000,
            )

    # ── Zero proceeds (sell at $0) ────────────────────────────────

    def test_sellSecurity_zeroPriceCents_raises(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        with pytest.raises(ValueError, match="Total proceeds must be non-zero"):
            fast_manager.sell_security(
                datetime(2026, 3, 1), "Free Sell",
                brokerage, checking, "VTI", 5, 0,
            )

    # ── Realized gain (gain_account provided) ─────────────────────

    def test_sellSecurity_withGainAccount_gainIsPositive(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        gain = fast_manager.add_account("Cap Gains", 4)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell With Gain",
            brokerage, checking, "VTI", 5, 29500,
            gain_account_id=gain,
        )
        fast_manager.generate_ledger()
        assert realized > 0
        gain_bal = fast_manager.get_display_balance(gain)
        assert abs(gain_bal - realized) < 2  # rounding tolerance

    def test_sellSecurity_largeGain_booksCorrectly(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 100, 10000)
        gain = fast_manager.add_account("Cap Gains", 4)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Big Gain",
            brokerage, checking, "VTI", 50, 50000,
            gain_account_id=gain,
        )
        fast_manager.generate_ledger()
        # Avg cost = 10000, cost of sold = 50 × 10000 = 500000
        # Proceeds = 50 × 50000 = 2500000
        # Realized = 2500000 - 500000 = 2000000
        assert realized == (50 * 50000) - (50 * 10000)
        gain_bal = fast_manager.get_display_balance(gain)
        assert abs(gain_bal - realized) < 2

    # ── Realized loss (sell below cost) ───────────────────────────

    def test_sellSecurity_withLossAccount_lossIsNegative(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 30000)
        loss = fast_manager.add_account("Trading Losses", 5)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell Low",
            brokerage, checking, "VTI", 10, 28000,
            gain_account_id=loss,
        )
        fast_manager.generate_ledger()
        assert realized < 0

    def test_sellSecurity_loss_dollarValueAccurate(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 30000)
        loss = fast_manager.add_account("Trading Losses", 5)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Loss",
            brokerage, checking, "VTI", 5, 25000,
            gain_account_id=loss,
        )
        fast_manager.generate_ledger()
        # Avg cost = 30000, cost of sold = 5 × 30000 = 150000
        # Proceeds = 5 × 25000 = 125000
        # Realized = 125000 - 150000 = -25000
        assert realized == (5 * 25000) - (5 * 30000)

    # ── Gain tracking with zero gain (sell at cost basis) ─────────

    def test_sellSecurity_atCostBasis_gainIsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        gain = fast_manager.add_account("Cap Gains", 4)
        # Sell at same price as cost basis — realized gain = 0
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "At Cost",
            brokerage, checking, "VTI", 5, 27500,
            gain_account_id=gain,
        )
        fast_manager.generate_ledger()
        assert realized == 0
        # No gain account entry when realized_gain is 0

    # ── Sell then buy more (reset cost basis) ─────────────────────

    def test_sellSecurity_sellThenBuyMore_resetsBasis(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 5000000), Split(brokerage, 5000000), Split(6, -10000000)],
        )
        # Buy 10 @ $275 → cost basis = 275000
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy",
                                  brokerage, checking, "VTI", 10, 27500)
        # Sell 5 @ $295 (gain)
        fast_manager.sell_security(datetime(2026, 3, 1), "Sell",
                                   brokerage, checking, "VTI", 5, 29500)
        # Buy 5 more @ $290 → new shares at new basis
        fast_manager.buy_security(datetime(2026, 4, 1), "Buy More",
                                  brokerage, checking, "VTI", 5, 29000)
        h = fast_manager.get_holdings(brokerage)[0]
        assert abs(h.shares - 10.0) < 0.001
        # Remaining 5 from original: cost = 5 × 27500 = 137500
        # New 5: 5 × 29000 = 145000
        # Total = 282500
        assert h.cost_basis_cents == (5 * 27500) + (5 * 29000)

    def test_sellSecurity_fullExitThenBuyBack_createsNewPosition(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 5000000), Split(brokerage, 5000000), Split(6, -10000000)],
        )
        fast_manager.buy_security(datetime(2026, 2, 1), "Buy",
                                  brokerage, checking, "VTI", 10, 27500)
        fast_manager.sell_security(datetime(2026, 3, 1), "Sell All",
                                   brokerage, checking, "VTI", 10, 29500)
        assert len(fast_manager.get_holdings(brokerage)) == 0
        # Buy back at higher price
        fast_manager.buy_security(datetime(2026, 4, 1), "Buy Back",
                                  brokerage, checking, "VTI", 15, 31000)
        h = fast_manager.get_holdings(brokerage)[0]
        assert h.shares == 15.0
        assert h.cost_basis_cents == 15 * 31000

    # ── Sell without gain_account (no explicit gain tracking) ─────

    def test_sellSecurity_noGainAccount_returnsRealizedGain(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 27500)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell",
            brokerage, checking, "VTI", 5, 29500,
        )
        fast_manager.generate_ledger()
        assert realized > 0
        # Gain is still computed and returned, just not booked in a P&L account

    def test_sellSecurity_noGainAccount_lossStillReturned(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 30000)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell Low",
            brokerage, checking, "VTI", 5, 25000,
        )
        fast_manager.generate_ledger()
        assert realized < 0

    # ── Sell from retirement / MESP subtypes ──────────────────────

    def test_sellSecurity_fromMespAccount_works(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        mesp = fast_manager.add_account("MESP", 1, account_subtype="mesp")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 10000000), Split(mesp, 10000000), Split(6, -20000000)],
        )
        fast_manager.buy_security(datetime(2026, 2, 1), "MESP Buy",
                                  mesp, checking, "MESP-MD-R1", 50, 10750)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "MESP Sell",
            mesp, checking, "MESP-MD-R1", 20, 11000,
        )
        h = fast_manager.get_holdings(mesp)[0]
        assert abs(h.shares - 30.0) < 0.001

    def test_sellSecurity_fromRetirementAccount_works(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        ira = fast_manager.add_account("Roth IRA", 1, account_subtype="retirement")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(checking, 5000000), Split(ira, 5000000), Split(6, -10000000)],
        )
        fast_manager.buy_security(datetime(2026, 2, 1), "IRA Buy",
                                  ira, checking, "VT", 200, 10500)
        txn_id, realized = fast_manager.sell_security(
            datetime(2026, 3, 1), "IRA Sell",
            ira, checking, "VT", 50, 11000,
        )
        h = fast_manager.get_holdings(ira)[0]
        assert abs(h.shares - 150.0) < 0.001


# ═══════════════════════════════════════════════════════════════════
# AvgCostBasis — (M=4 cyclomatic)
# ═══════════════════════════════════════════════════════════════════

class TestAvgCostBasis:
    """Average-cost-basis helper — exhaustive edge cases."""

    def test_avgCost_singleBuy_returnsInitialPrice(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        assert fast_manager._avg_cost_basis(aid, "VTI") == 27500.0

    def test_avgCost_twoBuys_computesWeightedAverage(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 1000000), Split(checking, 1000000), Split(6, -2000000)],
        )
        fast_manager.buy_security(datetime(2026, 2, 1), "B1",
                                  brokerage, checking, "VTI", 10, 10000)
        fast_manager.buy_security(datetime(2026, 3, 1), "B2",
                                  brokerage, checking, "VTI", 5, 20000)
        avg = fast_manager._avg_cost_basis(brokerage, "VTI")
        # (10*10000 + 5*20000) / (10+5) = 200000/15 = 13333.33
        assert abs(avg - 13333.33) < 1

    def test_avgCost_threeBuys_varyingPrices(
        self, fast_manager: AccountManager,
    ) -> None:
        checking = fast_manager.add_account("Checking", 1)
        brokerage = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.add_transaction(
            datetime(2026, 1, 1), "Fund",
            [Split(brokerage, 2000000), Split(checking, 2000000), Split(6, -4000000)],
        )
        fast_manager.buy_security(datetime(2026, 1, 1), "B1",
                                  brokerage, checking, "VTI", 100, 25000)
        fast_manager.buy_security(datetime(2026, 2, 1), "B2",
                                  brokerage, checking, "VTI", 50, 30000)
        fast_manager.buy_security(datetime(2026, 3, 1), "B3",
                                  brokerage, checking, "VTI", 25, 20000)
        avg = fast_manager._avg_cost_basis(brokerage, "VTI")
        expected = (100 * 25000 + 50 * 30000 + 25 * 20000) / (100 + 50 + 25)
        assert abs(avg - expected) < 1

    def test_avgCost_noHoldings_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        assert fast_manager._avg_cost_basis(aid, "VTI") == 0.0

    def test_avgCost_zeroShares_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 0.0, 0)
        assert fast_manager._avg_cost_basis(aid, "VTI") == 0.0

    def test_avgCost_zeroCost_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 100.0, 0)
        assert fast_manager._avg_cost_basis(aid, "VTI") == 0.0

    def test_avgCost_nonexistentAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager._avg_cost_basis(99999, "VTI") == 0.0

    def test_avgCost_nonexistentTicker_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        assert fast_manager._avg_cost_basis(aid, "AAPL") == 0.0

    def test_avgCost_fractionalShares_accurate(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        # 10.543 shares at total cost of 110703 cents
        fast_manager.set_holding(aid, "VTI", 10.543, 110703)
        avg = fast_manager._avg_cost_basis(aid, "VTI")
        expected = 110703 / 10.543
        assert abs(avg - expected) < 1

    def test_avgCost_roundingAfterSell(
        self, fast_manager: AccountManager,
    ) -> None:
        checking, brokerage = _fund_and_buy(fast_manager, "VTI", 10, 30000)
        fast_manager.sell_security(
            datetime(2026, 3, 1), "Sell", brokerage, checking, "VTI", 5, 31000,
        )
        # After selling half, avg cost should still be 30000 (unaffected by sale)
        avg = fast_manager._avg_cost_basis(brokerage, "VTI")
        assert abs(avg - 30000.0) < 1


# ═══════════════════════════════════════════════════════════════════
# PortfolioValue — (M=5 cyclomatic)
# ═══════════════════════════════════════════════════════════════════

class TestPortfolioValue:
    """Portfolio market value — exhaustive edge cases."""

    def test_portfolio_singleHolding_allPrices_returnsProduct(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        mv = fast_manager.portfolio_market_value(aid)
        assert mv == 10 * 29000

    def test_portfolio_missingPrice_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        assert fast_manager.portfolio_market_value(aid) is None

    def test_portfolio_multipleHoldings_allPrices_returnsSum(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.set_holding(aid, "AAPL", 5.0, 75000)
        fast_manager.set_holding(aid, "BND", 200.0, 1500000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        fast_manager.save_price("AAPL", "2026-05-13", 16500)
        fast_manager.save_price("BND", "2026-05-13", 7500)
        mv = fast_manager.portfolio_market_value(aid)
        assert mv == 10 * 29000 + 5 * 16500 + 200 * 7500

    def test_portfolio_oneOfMultipleMissing_returnsNone(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.0, 275000)
        fast_manager.set_holding(aid, "AAPL", 5.0, 75000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        # No price for AAPL
        assert fast_manager.portfolio_market_value(aid) is None

    def test_portfolio_emptyAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Empty", 1, account_subtype="brokerage")
        assert fast_manager.portfolio_market_value(aid) == 0

    def test_portfolio_nonexistentAccount_returnsZero(
        self, fast_manager: AccountManager,
    ) -> None:
        assert fast_manager.portfolio_market_value(99999) == 0

    def test_portfolio_fractionalShares_valueCalculated(
        self, fast_manager: AccountManager,
    ) -> None:
        aid = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        fast_manager.set_holding(aid, "VTI", 10.543, 110703)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        mv = fast_manager.portfolio_market_value(aid)
        # 10.543 × 29000 = 305747 (int floors)
        assert mv == int(10.543 * 29000)

    def test_portfolio_differentPricesAcrossAccounts(
        self, fast_manager: AccountManager,
    ) -> None:
        acct_a = fast_manager.add_account("Brokerage", 1, account_subtype="brokerage")
        acct_b = fast_manager.add_account("Roth IRA", 1, account_subtype="retirement")
        fast_manager.set_holding(acct_a, "VTI", 10.0, 275000)
        fast_manager.set_holding(acct_b, "VT", 200.0, 2100000)
        fast_manager.save_price("VTI", "2026-05-13", 29000)
        fast_manager.save_price("VT", "2026-05-13", 11000)
        mv_a = fast_manager.portfolio_market_value(acct_a)
        mv_b = fast_manager.portfolio_market_value(acct_b)
        assert mv_a == 10 * 29000
        assert mv_b == 200 * 11000
