#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Factory for loading server-type-specific Windows addon installer names."""

from nxdrive.drive import server_type as st


def get_addon_installer_name() -> str:
    """Get the addon installer executable name for the current server type."""
    config = st.get(st.get_default_key())
    return config.addon_installer_name or "drive-addons.exe"
