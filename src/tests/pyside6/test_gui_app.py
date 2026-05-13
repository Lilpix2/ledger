"""Component tests: PySide6 — main window structure.

Tests the PySide6 ``LedgerGUI`` main window. Currently tests against
the stub (which raises NotImplementedError) — these will pass once
the real implementation exists.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    pytest.skip("PySide6 not available (pip install PySide6)", allow_module_level=True)
    HAS_PYSIDE = False


class TestLedgerGUIStructure:
    """Main window structure tests.

    All tests currently expect NotImplementedError from the stub.
    Replace with real assertions once ``LedgerGUI`` is implemented.
    """

    def test_construct_raises_not_implemented(self, qt_app):
        """LedgerGUI stub raises NotImplementedError until implemented."""
        from ledger.gui_pyside.gui_app_pyside import LedgerGUI

        with pytest.raises(NotImplementedError):
            LedgerGUI("/tmp/nonexistent.db")
