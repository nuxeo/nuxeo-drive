# How to debug a functional test with the pydev server

- Copy `pysrc` from the PyDev eclipse plugin to your Pyhton libraries
- Rename it to `pydev`
- Add a `__init__.py` file in `pydev`

Typically:

    sudo cp -r ~/eclipse/plugins/org.python.pydev_3.0.0.201311051910/pysrc /usr/local/lib/python2.7/dist-packages
    sudo mv /usr/local/lib/python2.7/dist-packages/pysrc /usr/local/lib/python2.7/dist-packages/pydev
    sudo touch /usr/local/lib/python2.7/dist-packages/pydev/__init__.py

- Launch the pydev server from the Debug perspective
- Set the PYDEV_DEBUG environment variable to `True` on the test's Debug Configuration
- Debug the test!
