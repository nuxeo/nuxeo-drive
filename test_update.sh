
# Delete Nuxeo Drive config and files
rm -rf ~/.nuxeo-drive/ ~/Nuxeo\ Drive/

# Delete installed frozen apps
rm -rf ~/freeze/*

# Delete frozen apps from mock update site
rm -rf dist/nuxeo-drive-*

# Set version to 1.3.MMdd
sed -i "s/4/3/g" nuxeo-drive-client/nxdrive/__init__.py

# Freeze app and deploy it to mock update site
source ENV/bin/activate
python setup.py bdist_esky --dev --freeze --enable-appdata-dir=True

# Install frozen app
unzip dist/nuxeo-drive-1.3.0523.linux-x86_64.zip -d ~/freeze/

# Launch deployed app
~/freeze/ndrive --log-level-console=DEBUG --update-check-delay=4

