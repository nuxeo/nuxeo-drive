# How to package a portable and auto-updatable Python application

## Portability

- See [Welcome to The Hitchhiker’s Guide to Packaging](http://guide.python-distribute.org/)

- Can use [mippy](https://pypi.python.org/pypi/myppy) or [virtualenv](https://virtualenv.pypa.io/en/latest/virtualenv.html) for Python portability. Let's use `virtualenv`.

### Setting up virtualenv

See [latest documentation](https://virtualenv.pypa.io/en/latest/).

    sudo pip install virtualenv
    virtualenv ENV
    cp /usr/lib/python2.7/dist-packages/PyQt4 ENV/lib/python2.7/site-packages
    cp /usr/lib/python2.7/dist-packages/sip.so ENV/lib/python2.7/site-packages
    source ENV/bin/activate

### Installing requirements with pip

To satisfy `cx_Freeze`, the following options are needed:

    pip install -r requirements.txt --allow-external cx_Freeze --allow-unverified cx_Freeze

The packages will be installed in `ENV/lib/python2.7/site-packages`.

## Regular application freeze

### Windows / Linux

Run `cx_Freeze`:

    python setup.py build_exe --dev --freeze

### OS X

Install and run `py2app`:

    sudo pip install py2app
    python setup.py py2app --dev

## Esky freeze

[Esky](https://pypi.python.org/pypi/esky) is a framework that allows a frozen application to update itself.

### Windows / Linux

Run `esky`:

    python setup.py dist_esky --dev --freeze --enable-appdata-dir=True

### OS X

TODO

### Notes about bdist_esky options (vs cx_Freeze)

- `executables` => `scripts`
- `include_files` => `data_files` as a global `setup()` option
- No `packages` option in `bdist_esky` (especially nose => coverage related stuff)

### Other interesting features

- `bdist_esky_patch`: make small patches!
- Manages no write access on file system.

## Debugging a frozen application

Can use PyDev server:

- Copy `pysrc` form PyDev eclipse plugin to `ENV/lib/python2.7/site-packages`
- Rename it to `pydev`
- Add a `__init__.py` file in `pydev` 
- Launch PyDev server from the Debug perspective
- Add these lines where to break:

        import pydevd
        pydevd.settrace()

### TODO

- Check freeze under Windows and OS X: compare output, launch frozen app.
- Make MSI => other freeze options in setup?
- Review all setup options for all platforms (ex: check `py2app` with `data_files` removed from local options).
- What if not admin?
- Create (recurrent) Jira task to check if required packages need to be upgraded (in which case need to increase their version in `requirements.txt`).
- In `utils.find_resource_dir` => use `sys.executable`?
