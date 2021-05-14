"""
Application features that can be turned on/off on-demand.
Parameters listed here can be set locally and remotely.

Introduced in Nuxeo Drive 4.4.2.

Available parameters and introduced version:

- auto_update (4.4.2)
    Allow or disallow auto-updates.

- direct_edit (4.4.2)
    Allow or disallow Direct Edit.

- direct_transfer (4.4.2)
    Allow or disallow Direct Transfer.

- s3 (4.4.2)
    Allow or disallow using Amazon S3 direct uploads.

- synchronization (5.2.0)
    Enable or disable the synchronization features.

"""
from types import SimpleNamespace
from typing import List

Feature = SimpleNamespace(
    auto_update=True,
    synchronization=False,
    direct_edit=True,
    direct_transfer=True,
    s3=False,
)

Beta: List[str] = ["s3"]

DisabledFeatures: List[str] = []
