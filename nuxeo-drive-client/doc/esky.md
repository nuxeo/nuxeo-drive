# Build and package a portable and auto-updatable Python appplication

## Portability:
- See [Welcome to The Hitchhiker’s Guide to Packaging](http://guide.python-distribute.org/)
- Use mippy / virtualenv => Python portability => virtualenv suites fine
- Use Distribute instead of distutils? No need for now.

### Virtualenv:

Setup

    virtualenv ENV
    source ENV/bin/activate
    pip install -r requirements.txt --allow-external cx_Freeze --allow-unverified cx_Freeze
    cp /usr/lib/python2.7/dist-packages/PyQt4 ENV/lib/python2.7/site-packages
    cp /usr/lib/python2.7/dist-packages/sip.so ENV/lib/python2.7/site-packages

Debug with PyDev server:

- Copy pysrc form pydev eclipse plugin to ENV/lib/python2.7/site-packages + rename to pydev + add __init__.py
- Launch PyDev server in Debug perspective
- Add these lines where to break:
    import pydevd
    pydevd.settrace()


Run cx_Freeze:

    python setup.py build_exe --freeze --dev

## Esky freeze

### Features

- bdist\_esky_patch => small patches!!
- manages no write access on FileSystem!
- app.find_update() => is there an update? If yes => prompt UI, else...
- app.cleanup()

### bdist_esky options (vs cx_Freeze)

- executables => scripts
- include\_files => data\_files as a global setup() option => check py2app: removed from local options
- no "packages" option in bdist\_esky (especially nose => coverage related stuff, cf. diff below)

### Run freeze:

Linux/Windows:

    python setup.py dist_esky --dev

Diff with regular (non-esky) freeze:

    (ENV)ataillefer@taillefer-xps:~/sources/nuxeo/addons/nuxeo-drive/dist/test$ diff nuxeo-drive-1.3.0407.linux-x86_64/ ~/tmp/exe.linux-x86_64-2.7/
    Seulement dans /home/ataillefer/tmp/exe.linux-x86_64-2.7/: coverage.tracer.so
    Seulement dans nuxeo-drive-1.3.0407.linux-x86_64/: esky-files
    Seulement dans /home/ataillefer/tmp/exe.linux-x86_64-2.7/: _hotshot.so
    Les fichiers binaires nuxeo-drive-1.3.0407.linux-x86_64/library.zip et /home/ataillefer/tmp/exe.linux-x86_64-2.7/library.zip sont différents
    
    (ENV)ataillefer@taillefer-xps:~/sources/nuxeo/addons/nuxeo-drive$ sudo diff dist/test/library/ ~/tmp/library/
    Seulement dans /home/ataillefer/tmp/library/: BaseHTTPServer.pyc
    Seulement dans /home/ataillefer/tmp/library/: BUILD_CONSTANTS.pyc
    Seulement dans /home/ataillefer/tmp/library/: cgi.pyc
    Les fichiers binaires dist/test/library/cookielib.pyc et /home/ataillefer/tmp/library/cookielib.pyc sont différents
    Seulement dans /home/ataillefer/tmp/library/: coverage
    Seulement dans dist/test/library/: esky
    Seulement dans /home/ataillefer/tmp/library/: hotshot
    Seulement dans /home/ataillefer/tmp/library/: md5.pyc
    Les fichiers binaires dist/test/library/ndrive__main__.pyc et /home/ataillefer/tmp/library/ndrive__main__.pyc sont différents
    Seulement dans /home/ataillefer/tmp/library/: profile.pyc
    Seulement dans /home/ataillefer/tmp/library/: setuptools
    Seulement dans /home/ataillefer/tmp/library/: SimpleHTTPServer.pyc

### TODO

- includes/excludes not needed for bdist\_esky, in fact whole --freeze option (but WIN?)!
- Check freeze under Win / py2app under OS X: compare output, launch ndrive
- OSX
- Make MSI/ DMG? (other setup?)
- Works if not admin?
- Create (recurrent) Jira task to check if required modules need to be upgraded (increase version in requirements.txt)
- utils.find_resource_dir => use sys.executable?
