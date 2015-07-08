
## Nautilus

### Install Nautilus required addon

    apt-get install python-nautilus

### Install the extension

    cp nuxeo-drive-client/doc/nautilus/contextual_menu.py ~/.local/share/nautilus-python/extensions

## Windows

Automatically handled at startup using registry by

    nxdrive.register_contextual_menu.register_contextual_menu
