"""PySide6 component test fixtures.

Provides ``qt_app`` fixture for QApplication lifecycle (skipped when
no display is available) and helper functions for finding widgets.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest


def _has_qt_display() -> bool:
    """Check if PySide6 is available; configure offscreen mode for headless."""
    try:
        # Use offscreen platform for headless environments
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        # Quick smoke test
        _test_app = QApplication.instance() or QApplication([])
        return True
    except Exception:
        return False


HAS_QT_DISPLAY = _has_qt_display()


@pytest.fixture(scope="session")
def qt_app():
    """Create a single QApplication instance.

    Skips the test if PySide6 isn't installed or there's no display.
    """
    if not HAS_QT_DISPLAY:
        pytest.skip("No Qt display available (set DISPLAY or use xvfb-run)")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_success():
    """A ``MagicMock`` that can be passed as ``on_success`` callback."""
    return MagicMock()


# ── Widget tree helpers ─────────────────────────────────


def find_widget(parent: Any, klass: type, text: str | None = None) -> Any | None:
    """Find a child widget by type and optional text/label."""
    if not HAS_QT_DISPLAY:
        return None
    from PySide6.QtWidgets import QPushButton, QLabel

    for child in parent.findChildren(klass):
        if text is None:
            return child
        if isinstance(child, QPushButton):
            if child.text() == text:
                return child
        if isinstance(child, QLabel):
            if child.text() == text:
                return child
    return None


def click_button(parent: Any, text: str) -> bool:
    """Find a ``QPushButton`` by text and click it."""
    btn = find_widget(parent, QPushButton, text)
    if btn is None:
        return False
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    return True
