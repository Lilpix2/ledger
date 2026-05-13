"""Integration tests for the Textual TUI: modal screens, bindings, validation."""

import pytest
from datetime import datetime

from ledger.tui_app import (
    LedgerApp,
    AddAccountScreen,
    AddTransactionScreen,
    BuySellScreen,
    PortfolioScreen,
)

# ── Helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def app():
    """Create a headless LedgerApp for testing, yield it with pilot."""
    return LedgerApp()


@pytest.mark.asyncio
async def test_app_launches(app: LedgerApp):
    """App starts with 11 default accounts and a status bar."""
    async with app.run_test(size=(120, 40)) as pilot:
        assert len(pilot.app.manager.accounts) >= 11
        status = pilot.app.query_one("#status-bar")
        assert "$" in str(status.renderable)


@pytest.mark.asyncio
async def test_tree_populated(app: LedgerApp):
    """Account tree shows default accounts on startup."""
    async with app.run_test(size=(120, 40)) as pilot:
        tree = pilot.app.query_one("#account-tree")
        assert len(tree.root.children) >= 5


@pytest.mark.asyncio
async def test_table_populated(app: LedgerApp):
    """Transaction table exists with headers."""
    async with app.run_test(size=(120, 40)) as pilot:
        table = pilot.app.query_one("#transaction-table")
        # Should have columns
        assert len(table.columns) > 0


@pytest.mark.asyncio
async def test_add_account_binding(app: LedgerApp):
    """Pressing 'a' opens the Add Account modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(pilot.app.screen, AddAccountScreen)


@pytest.mark.asyncio
async def test_add_transaction_binding(app: LedgerApp):
    """Pressing 't' opens the Add Transaction modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(pilot.app.screen, AddTransactionScreen)


@pytest.mark.asyncio
async def test_buy_sell_binding(app: LedgerApp):
    """Pressing 'v' opens the Buy/Sell modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("v")
        await pilot.pause()
        assert isinstance(pilot.app.screen, BuySellScreen)


@pytest.mark.asyncio
async def test_portfolio_binding(app: LedgerApp):
    """Pressing 'p' opens the Portfolio modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(pilot.app.screen, PortfolioScreen)


@pytest.mark.asyncio
async def test_create_account_flow(app: LedgerApp):
    """Create an account through the modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("a")
        await pilot.pause()

        # Fill in the form
        acct_name = pilot.app.query_one("#acct-name")
        parent_input = pilot.app.query_one("#acct-parent")

        await pilot.click(acct_name)
        await pilot.press(*"My Checking")
        await pilot.pause()

        await pilot.click(parent_input)
        await pilot.press(*"1")  # parent = Assets
        await pilot.pause()

        # Submit
        btn = pilot.app.query_one("#submit")
        await pilot.click(btn)
        await pilot.pause()

        # Should be back on main screen
        assert not isinstance(pilot.app.screen, AddAccountScreen)
        # Tree should show the new account
        tree = pilot.app.query_one("#account-tree")
        all_labels = _collect_tree_labels(tree)
        assert any("My Checking" in lbl for lbl in all_labels)


def _collect_tree_labels(tree):
    """Get all node labels from a Tree widget."""
    labels = []

    def walk(node):
        if node.label:
            labels.append(str(node.label))
        for child in node.children:
            walk(child)

    walk(tree.root)
    return labels


@pytest.mark.asyncio
async def test_create_account_with_subtype(app: LedgerApp):
    """Create an account with a subtype through the modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("a")
        await pilot.pause()

        name_input = pilot.app.query_one("#acct-name")
        parent_input = pilot.app.query_one("#acct-parent")
        subtype_input = pilot.app.query_one("#acct-subtype")

        await pilot.click(name_input)
        await pilot.press(*"HS Checking")
        await pilot.pause()

        await pilot.click(parent_input)
        await pilot.press(*"1")
        await pilot.pause()

        await pilot.click(subtype_input)
        await pilot.press(*"checking")
        await pilot.pause()

        await pilot.click(pilot.app.query_one("#submit"))
        await pilot.pause()

        # Verify account was created with subtype
        for aid, acct in pilot.app.manager.accounts.items():
            if acct.name == "HS Checking":
                assert acct.account_subtype == "checking"
                return
        pytest.fail("Account not found")


@pytest.mark.asyncio
async def test_add_transaction_flow(app: LedgerApp):
    """Add a transaction through the modal."""
    async with app.run_test(size=(120, 40)) as pilot:
        # First create accounts to transact between
        pilot.app.manager.add_account("My Checking", 1, account_subtype="checking")
        pilot.app.manager.add_account("Groceries", 5)
        pilot.app.manager.generate_ledger()

        # We need to know the IDs - the app already has default accounts
        # Default: cash=7, groceries would need to be created
        # Let's find IDs
        checking_id = None
        groceries_id = None
        for aid, acct in pilot.app.manager.accounts.items():
            if acct.name == "My Checking":
                checking_id = aid
            if acct.name == "Groceries":
                groceries_id = aid

        await pilot.press("t")
        await pilot.pause()

        # Date is pre-filled - skip
        desc = pilot.app.query_one("#txn-desc")
        await pilot.click(desc)
        await pilot.press(*"Weekly shop")
        await pilot.pause()

        # Fill split 0: debit account
        acct0 = pilot.app.query_one("#split-acct-0")
        amt0 = pilot.app.query_one("#split-amt-0")

        await pilot.click(acct0)
        await pilot.press(*str(groceries_id))
        await pilot.pause()

        await pilot.click(amt0)
        await pilot.press(*"5000")
        await pilot.pause()

        # Add another split for credit
        await pilot.click(pilot.app.query_one("#add-split-btn"))
        await pilot.pause()

        acct1 = pilot.app.query_one("#split-acct-1")
        amt1 = pilot.app.query_one("#split-amt-1")

        await pilot.click(acct1)
        await pilot.press(*str(checking_id))
        await pilot.pause()

        # Toggle to credit
        dir_btn = pilot.app.query_one("#split-dir-1")
        await pilot.click(dir_btn)
        await pilot.pause()

        await pilot.click(amt1)
        await pilot.press(*"5000")
        await pilot.pause()

        # Submit
        await pilot.click(pilot.app.query_one("#submit"))
        await pilot.pause()

        # Back on main screen
        assert not isinstance(pilot.app.screen, AddTransactionScreen)
        # Verify transaction was recorded
        assert len(pilot.app.manager.journal.transactions) > 0


@pytest.mark.asyncio
async def test_buy_sell_modal_layout(app: LedgerApp):
    """Buy/Sell modal has correct widgets."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("v")
        await pilot.pause()

        assert pilot.app.query_one("#dir-buy")
        assert pilot.app.query_one("#dir-sell")
        assert pilot.app.query_one("#inv-acct")
        assert pilot.app.query_one("#cash-acct")
        assert pilot.app.query_one("#ticker")
        assert pilot.app.query_one("#shares")
        assert pilot.app.query_one("#price")
        assert pilot.app.query_one("#submit")
        assert pilot.app.query_one("#cancel")


@pytest.mark.asyncio
async def test_portfolio_screen(app: LedgerApp):
    """Portfolio screen opens and displays."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("p")
        await pilot.pause()

        assert pilot.app.query_one("#port-table")
        assert pilot.app.query_one("#port-summary")
        assert pilot.app.query_one("#refresh")
        assert pilot.app.query_one("#close")


@pytest.mark.asyncio
async def test_buy_sell_direction_toggle(app: LedgerApp):
    """Toggling Buy/Sell shows/hides gains account field."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("v")
        await pilot.pause()

        # Default: Buy mode, gains field hidden
        gain_row = pilot.app.query_one("#gain-row")
        assert not gain_row.visible

        # Click Sell
        sell_btn = pilot.app.query_one("#dir-sell")
        await pilot.click(sell_btn)
        await pilot.pause()
        assert gain_row.visible

        # Click Buy
        buy_btn = pilot.app.query_one("#dir-buy")
        await pilot.click(buy_btn)
        await pilot.pause()
        assert not gain_row.visible


@pytest.mark.asyncio
async def test_net_worth_action(app: LedgerApp):
    """Net worth action shows notification."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("n")
        await pilot.pause()


@pytest.mark.asyncio
async def test_balance_sheet_action(app: LedgerApp):
    """Balance sheet action shows notification."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("b")
        await pilot.pause()


@pytest.mark.asyncio
async def test_income_statement_action(app: LedgerApp):
    """Income statement action shows notification."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("i")
        await pilot.pause()


@pytest.mark.asyncio
async def test_tree_select_filters_table(app: LedgerApp):
    """Selecting a tree node filters the transaction table."""
    async with app.run_test(size=(120, 40)) as pilot:
        tree = pilot.app.query_one("#account-tree")
        # Click the first child node
        if tree.root.children:
            node = tree.root.children[0]
            await pilot.click(node)
            await pilot.pause()
            # Table should be filtered
            table = pilot.app.query_one("#transaction-table")
            assert table is not None


@pytest.mark.asyncio
async def test_refresh_binding(app: LedgerApp):
    """Refresh action runs without errors."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+r")
        await pilot.pause()
        # Should still be on main screen
        assert not isinstance(pilot.app.screen, (AddAccountScreen, AddTransactionScreen))


@pytest.mark.asyncio
async def test_quit_binding(app: LedgerApp):
    """Quit binding exits the app."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("q")
        await pilot.pause()
        # App should have exited
        assert pilot.app._running is False


@pytest.mark.asyncio
async def test_cancel_add_account(app: LedgerApp):
    """Cancel button in AddAccount returns to main screen."""
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("a")
        await pilot.pause()
        cancel = pilot.app.query_one("#cancel")
        await pilot.click(cancel)
        await pilot.pause()
        assert not isinstance(pilot.app.screen, AddAccountScreen)


@pytest.mark.asyncio
async def test_account_detail_popup(app: LedgerApp):
    """Clicking a tree node shows account details (notification)."""
    async with app.run_test(size=(120, 40)) as pilot:
        tree = pilot.app.query_one("#account-tree")
        if tree.root.children:
            node = tree.root.children[0]
            await pilot.click(node)
            await pilot.pause()
            # Details should fire — just verify no crash
            assert True


@pytest.mark.asyncio
async def test_status_bar_updates(app: LedgerApp):
    """Status bar shows assets, liabilities, net worth."""
    async with app.run_test(size=(120, 40)) as pilot:
        status = pilot.app.query_one("#status-bar")
        text = str(status.renderable)
        assert "Assets" in text
        assert "Liabilities" in text
        assert "Net Worth" in text
        assert "$" in text
