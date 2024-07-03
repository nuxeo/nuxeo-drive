"""
General application state.
Introduced in Nuxeo Drive 4.4.4.

Available parameters:

- about_to_quit (4.4.4)
    This is set from the GUI when clicking on Quit.

- has_crashed (4.4.5)
    This state is set at the start of the application to know if it has crashed at the previous run.

"""
from types import SimpleNamespace

State = SimpleNamespace(about_to_quit=False, crash_details="", has_crashed=False)
