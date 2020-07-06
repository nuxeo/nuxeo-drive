"""
Application features that can be turned on/off on-demand.
Parameters listed here can be set locally and remotely.

Introduced in Nuxeo Drive 4.4.2.

Available parameters and introduced version:

- auto_updates (4.4.2)
    Allow or disallow auto-updates.

- direct_edit (4.4.2)
    Allow or disallow Direct Edit.

- direct_transfer (4.4.2)
    Allow or disallow Direct Transfer.

- s3 (4.4.2)
    Allow or disallow using Amazon S3 direct uploads.

"""
from types import SimpleNamespace

Feature = SimpleNamespace(
    auto_update=True, direct_edit=True, direct_transfer=False, s3=False,
)

Beta = ["direct_transfer", "s3"]

DisabledFeatures = ["s3"]
