# GNU/Linux

## Nautilus

Install required Nautilus addons:

    apt install python-nautilus nautilus-emblems

Create custom emblems:

    mkdir -p ~/.icons/hicolor/48x48/emblems
    cp nuxeo-drive-client/nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

Install the extension:

    cp nuxeo-drive-client/nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions

# macOS

TODO

# Windows

TODO

Windows Explorer overlay using Python based on [Add my own icon overlays](http://timgolden.me.uk/python/win32_how_do_i/add-my-own-icon-overlays.html)

See [pyoverlay.py](https://github.com/nuxeo/nuxeo-drive/tree/master/nuxeo-drive-client/nxdrive/overlay/win32/pyoverlay.py)
