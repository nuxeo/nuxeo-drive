#!/usr/bin/env bash
#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

nautilus -q

# Icon overlay, uncomment when https://hyland.atlassian.net/browse/NXDRIVE-374 is fixed
#cp nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions
#cp nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

# Contextual menu
cp doc/nautilus/contextual_menu.py ~/.local/share/nautilus-python/extensions

nautilus&
