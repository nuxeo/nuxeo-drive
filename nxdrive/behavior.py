"""
Application behavior that can be turned on/off on-demand.
Parameters listed here cannot be set locally: only the server
has rights to change values.

Introduced in Nuxeo Drive 4.4.2.

Available parameters and introduced version:

- server_deletion (4.4.2)
    Allow or disallow server deletions.

"""
from types import SimpleNamespace

Behavior = SimpleNamespace(server_deletion=True)
