"""Functional tests for nxdrive.gui.systray module – SystrayWindow._on_active_changed."""

from unittest.mock import patch

from ...markers import not_linux


@not_linux(reason="Qt GUI tests don't work reliably on Linux")
def test_on_active_changed_hides_when_inactive():
    """Window should hide itself when it loses focus (isActive returns False)."""
    from nxdrive.gui.systray import SystrayWindow

    with patch.object(SystrayWindow, "__init__", lambda self, parent=None: None):
        window = SystrayWindow.__new__(SystrayWindow)

        hidden = []

        def fake_hide():
            hidden.append(True)

        window.hide = fake_hide
        window.isActive = lambda: False

        window._on_active_changed()

    assert hidden == [True]


@not_linux(reason="Qt GUI tests don't work reliably on Linux")
def test_on_active_changed_does_not_hide_when_active():
    """Window should NOT hide itself when it is still active."""
    from nxdrive.gui.systray import SystrayWindow

    with patch.object(SystrayWindow, "__init__", lambda self, parent=None: None):
        window = SystrayWindow.__new__(SystrayWindow)

        hidden = []

        def fake_hide():
            hidden.append(True)

        window.hide = fake_hide
        window.isActive = lambda: True

        window._on_active_changed()

    assert hidden == []
