
# Set version to 1.4.MMdd
sed -i "s/3/4/g" nuxeo-drive-client/nxdrive/__init__.py

# Freeze app and deploy it to mock update site
source ENV/bin/activate
python setup.py bdist_esky --dev --freeze --enable-appdata-dir=True

