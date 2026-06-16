"""Configuration for GUI functional tests - force serial execution on macOS."""

import platform


def pytest_configure(config):
    """Force serial execution for GUI tests on macOS to avoid xdist worker crashes.

    GUI tests use PyQt6 and xdist parallelism with many engine worker threads
    causes thread/event-loop collisions leading to worker crashes on macOS.
    """
    if platform.system() == "Darwin":
        # Override xdist to run serially for GUI tests
        config.option.dist = "no"
        if hasattr(config.option, "numprocesses"):
            config.option.numprocesses = 1
