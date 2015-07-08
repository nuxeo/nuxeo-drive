nautilus -q

# Icon overlay, uncomment when https://jira.nuxeo.com/browse/NXDRIVE-374 is fixed
#cp nuxeo-drive-client/nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions
#cp nuxeo-drive-client/nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

# Contextual menu
cp nuxeo-drive-client/doc/nautilus/contextual_menu.py ~/.local/share/nautilus-python/extensions

nautilus&

