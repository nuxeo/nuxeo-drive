"""Factory for loading server-type-specific macOS FinderSync configurations."""

from typing import Tuple

from nxdrive.drive import server_type as st


def get_agent_template() -> str:
    """Get the launch agent plist template for the current server type."""
    config = st.get(st.get_default_key())
    return config.findersync_agent_template or ""


def get_findersync_ids() -> Tuple[str, str]:
    """Get the FinderSync bundle ID suffix and app extension name for the current server type.
    
    Returns:
        Tuple of (bundle_id_suffix, appex_name)
    """
    config = st.get(st.get_default_key())
    return config.findersync_bundle_id_suffix, config.findersync_appex_name
