"""E2E test fixtures for PySide6 main window tests."""
from __future__ import annotations

import os

import pytest

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


@pytest.fixture(scope="session")
def qt_app():
    """Create a single QApplication instance for the entire test session."""
    if not HAS_PYSIDE:
        pytest.skip("PySide6 not available (pip install PySide6)")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
