"""Component test fixtures for tkinter widget tests.

Provides ``tk_root`` fixture for widget instantiation without ``mainloop()``,
and helper functions for navigating the widget tree in black-box style.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

try:
    import tkinter as tk
    from tkinter import ttk

    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    tk = None
    ttk = None


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tk_root():
    """Create a hidden Tk root for widget instantiation.

    All dialogs and widgets in this module create Toplevels/frames from
    this root. ``mainloop()`` is never called — we interact with widgets
    programmatically.
    """
    if not HAS_TKINTER:
        pytest.skip("tkinter not available (install python3-tk)")
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


# ── Widget-tree navigation helpers (black-box) ─────────────────────


def walk(parent: tk.Widget | Any) -> Any:
    """Depth-first traversal yielding every descendant."""
    yield parent
    for child in parent.winfo_children():
        yield from walk(child)


def first_widget(
    parent: tk.Widget | Any,
    klass: type,
    text: str | None = None,
) -> Any | None:
    """First descendant matching *klass*, optionally matching label text."""
    for w in walk(parent):
        if not isinstance(w, klass):
            continue
        if text is None:
            return w
        try:
            if isinstance(w, (ttk.Button, ttk.Label, ttk.Checkbutton, ttk.Radiobutton)):
                if str(w.cget("text")) == text:
                    return w
        except tk.TclError:
            pass
    return None


def all_widgets(
    parent: tk.Widget | Any,
    klass: type,
    text: str | None = None,
) -> list:
    """All descendant widgets matching *klass*, optionally by label text."""
    result: list = []
    for w in walk(parent):
        if not isinstance(w, klass):
            continue
        if text is None:
            result.append(w)
            continue
        try:
            if isinstance(w, (ttk.Button, ttk.Label, ttk.Checkbutton, ttk.Radiobutton)):
                if str(w.cget("text")) == text:
                    result.append(w)
        except tk.TclError:
            pass
    return result


def first_entry(parent: tk.Widget | Any) -> ttk.Entry | None:
    """First plain ``ttk.Entry`` (not Combobox) in the widget tree."""
    for w in walk(parent):
        if isinstance(w, ttk.Entry):
            if isinstance(w, ttk.Combobox):
                continue
            return w
    return None


def set_entry_text(entry: ttk.Entry, text: str) -> None:
    """Set an Entry's text by delete+insert (black-box friendly)."""
    entry.delete(0, tk.END)
    entry.insert(0, text)


def button_invoke(parent: tk.Widget | Any, label: str) -> bool:
    """Find a ``ttk.Button`` by label and invoke it. Returns True on success."""
    btn = first_widget(parent, ttk.Button, label)
    if btn is None:
        return False
    btn.invoke()
    return True


# ── Mock presets ────────────────────────────────────────────────────


@pytest.fixture
def mock_success():
    """A ``Mock`` that can be passed as ``on_success`` callback."""
    return MagicMock()
