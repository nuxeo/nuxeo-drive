
## Setup

### Install required Nautilus addons 

    apt-get install python-nautilus
    apt-get install nautilus-emblems

### Create custom emblems

    mkdir -p ~/.icons/hicolor/48x48/emblems

    copy files from the nxdrive/data/icons/overlay/nautilus directory

### Install the extension

Copy python file in target directory :

    cp file_info_updater.py ~/.local/share/nautilus-python/extensions/.
