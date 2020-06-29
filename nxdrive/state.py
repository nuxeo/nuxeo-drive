# coding: utf-8
"""
General application state.
Introduced in Nuxeo Drive 4.4.4.

Available parameters:

- about_to_quit (4.4.4)
    This is set from the GUI when clicking on Quit.

- dt_remote_link (4.4.4)
    The HTML link pointing to the current Direct Transfer remote path.

"""
from types import SimpleNamespace

State = SimpleNamespace(about_to_quit=False, dt_remote_link="")
