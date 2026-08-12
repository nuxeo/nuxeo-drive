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
    auto_update=False,
    synchronization=False,
    direct_edit=True,
    direct_transfer=True,
    document_type_selection=False,
    tasks_management=False,
    s3=False,
)

Beta: List[str] = []

DisabledFeatures: List[str] = []


def apply_server_type_restrictions(server_type: str) -> None:
    """Disable features not available for the given server type.

    The list of disabled features is read from the server-type registry
    so that ``drive/`` has no hard-coded knowledge of any server type.
    """
    from nxdrive.drive.server_type import get

    config = get(server_type)
    for feature_name in config.disabled_features:
        setattr(Feature, feature_name, False)
        if feature_name not in DisabledFeatures:
            DisabledFeatures.append(feature_name)
