# coding: utf-8
"""
General application state.
Introduced in Nuxeo Drive 4.5.0.

Available parameters:

- about_to_quit
    This is set from the GUI when clicking on Quit.

"""
from types import SimpleNamespace

State = SimpleNamespace(about_to_quit=False)
