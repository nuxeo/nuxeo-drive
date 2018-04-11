#!/usr/bin/env bash
nautilus -q

# Icon overlay, uncomment when https://jira.nuxeo.com/browse/NXDRIVE-374 is fixed
#cp nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions
#cp nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

# Contextual menu
cp doc/nautilus/contextual_menu.py ~/.local/share/nautilus-python/extensions

nautilus&

