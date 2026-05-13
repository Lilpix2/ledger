"""
PySide6 dialogs for the double-entry ledger system.

Stub module for TDD — all classes raise NotImplementedError.
"""

from __future__ import annotations

from typing import Callable, Any


class AccountDialog:
    """Stub: will be a QDialog subclass.

    __init__(manager, on_success, edit_acct=None, edit_acct_id=None)
    """

    def __init__(
        self,
        manager: Any,
        on_success: Callable[[], None],
        edit_acct: Any = None,
        edit_acct_id: int | None = None,
    ) -> None:
        raise NotImplementedError("PySide6 AccountDialog not implemented yet")


class TransactionDialog:
    """Stub: will be a QDialog subclass.

    __init__(manager, on_success, edit_txn=None, edit_txn_id=None)
    """

    def __init__(
        self,
        manager: Any,
        on_success: Callable[[], None],
        edit_txn: Any = None,
        edit_txn_id: int | None = None,
    ) -> None:
        raise NotImplementedError("PySide6 TransactionDialog not implemented yet")


class BuySellDialog:
    """Stub: will be a QDialog subclass.

    __init__(manager, on_success)
    """

    def __init__(
        self,
        manager: Any,
        on_success: Callable[[], None],
    ) -> None:
        raise NotImplementedError("PySide6 BuySellDialog not implemented yet")


class DeleteAccountDialog:
    """Stub: will be a QDialog subclass.

    __init__(manager, acct_id, on_success)
    """

    def __init__(
        self,
        manager: Any,
        acct_id: int,
        on_success: Callable[[], None],
    ) -> None:
        raise NotImplementedError("PySide6 DeleteAccountDialog not implemented yet")
