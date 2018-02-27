# Support

Here is a page where you can see the OS vendors and versions as well as the browsers we are currently supporting; but also the Python version we are currently using.

## OS

List of officially supported platform vendors and versions:

- macOS >= 10.10, 64 bits
- Windows 7, both 32 and 64 bits
- Windows 8, both 32 and 64 bits
- Windows 8.1, both 32 and 64 bits
- Windows 10, both 32 and 64 bits

History:

- `2018-02-23`: dropped support for macOS 10.4 - 10.9
- `2017-04-11`: dropped support for Windows Vista
- `2014-04-08`: dropped support for Windows XP

### GNU/Linux

GNU/Linux support is a bit more complicated, but our developers are using Debian 8+ and Ubuntu 16.04+ on a daily basis.
It will depends of the current distribution support of PyQt4 and its WebKit plugin.

As those packages was removed on may 2015, you will have to compile yourself needed libraries.
You can find how we are doing to do so by reading [deployment.md](https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md) and the related Shell and PowerShell scripts.

_Note_: this is a temporary issue because when we will move to Python 3 and PyQt5, we will be able to create official packages for the most used distributions.

## Browsers

### Known limitations

With the Safari browser, the DirectEdit feature can be unstable (see [NXDRIVE-972](https://jira.nuxeo.com/browse/NXDRIVE-972)).
We recommend using recent versions of Firefox or Chrome for the best experience.

## Python

Nuxeo Drive is not a module but a whole package containing its own Python version and all dependencies.
If you want to use the module version as a basic module for your own software, please keep in mind that we do not offer support for dropped Python versions.

It may evolve quickly without notification as we are following the Python development cycle for the current used branch.
 
As of now, we are using the __Python 2.7__.

History:

- `2014-??-??`: dropped support for Python 2.6
