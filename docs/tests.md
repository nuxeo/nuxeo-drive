# How to debug a functional test with the pydev server

- Copy `pysrc` from the PyDev eclipse plugin to your Python libraries
- Rename it to `pydev`
- Add a `__init__.py` file in `pydev`

Typically:

    sudo cp -r ~/eclipse/plugins/org.python.pydev_3.0.0.201311051910/pysrc /usr/local/lib/python2.7/dist-packages
    sudo mv /usr/local/lib/python2.7/dist-packages/pysrc /usr/local/lib/python2.7/dist-packages/pydev
    sudo touch /usr/local/lib/python2.7/dist-packages/pydev/__init__.py

- Launch the pydev server from the Debug perspective
- Set the PYDEV_DEBUG environment variable to `True` on the test's Debug Configuration
- Debug the test!

# How to debug multi-threaded unit tests

Add these lines where you want to break:

    import pydevd
    pydevd.settrace('localhost', trace_only_current_thread=False)

# How to profile a method with PyVmMonitor

- Install pyvmmonitor in /opt
- Add this code before the method

    import sys
    sys.path.append('/opt/pyvmmonitor/public_api')
    import pyvmmonitor
    @pyvmmonitor.profile_method

- Open PyVmMonitor

    /opt/pyvmmonitor/pyvmmonitor-ui &

- Run the test and check the stats
