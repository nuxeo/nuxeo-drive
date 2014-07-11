nautilus -q

# Icon overlay
cp nuxeo-drive-client/nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions/.
cp nuxeo-drive-client/nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems/.

# Contextual menu
cp nuxeo-drive-client/nxdrive/overlay/nautilus/metadata_edit.py ~/.local/share/nautilus-python/extensions/.

nautilus&

