# Deployment Script

We are using scripts to automate the isolated environment creation. With only one script, you will be able to setup the environment, launch the tests suite and build the Drive package.

You could modify these scripts, but we will not be able to do support, these are the official way to manage the Drive ecosystem.

Finally, scripts names are referring to Jenkins, but you can always execute them on your personal computer or outside a Jenkins job.

## GNU/Linux, macOS

### Usage

    sh tools/$OSI/deploy_jenkins_slave.sh [ARG]

Where `$OSI` is one of: `linux`, `osx`.

Possible `ARG`:

    --build: freeze the client into self-hosted binary package
    --build-ext: build the FinderSync extension (macOS only)
    --start: start Nuxeo Drive
    --tests: launch the tests suite

Executing the script without argument will setup/update the isolated environment.

### Dependencies:

For both OSes, see [pyenv](https://github.com/yyuu/pyenv/wiki/Common-build-problems#requirements) requirements.

#### macOS

You will also need to install the Qt4 library, using HomeBrew:

	brew install cartr/qt4/qt-webkit@2.3

#### GNU/Linux

You will also need to install the Qt4 qmake tool and the Qt4 library:

	apt install qt4-make libqt4-dev libqtwebkit-dev
	# For debug version only
	apt install libqt4-dbg libqtwebkit4-dbg

## Windows

**PowerShell 4.0 or above** is required to run this script. You can find installation instructions [here](https://docs.microsoft.com/en-us/powershell/scripting/setup/installing-windows-powershell).

### Usage

    powershell .\tools\windows\deploy_jenkins_slave.ps1 [ARG] -direct

Possible `ARG`:

    -build: freeze the client into self-hosted binary package
    -start: start Nuxeo Drive
    -tests: launch the tests suite

Executing the script without argument will setup.update the isolated environment.

### Dependencies:

- [MinGW-w64](https://sourceforge.net/projects/mingw-w64/files/Toolchains%20targetting%20Win32/Personal%20Builds/mingw-builds/4.8.2/threads-posix/dwarf/i686-4.8.2-release-posix-dwarf-rt_v3-rev3.7z/download);
- [Qt 4.8.7 open-source](https://download.qt.io/official_releases/qt/4.8/4.8.7/qt-opensource-windows-x86-mingw482-4.8.7.exe);
- [Inno Setup 5.5.9 (u)](http://www.jrsoftware.org/download.php/is-unicode.exe) to create the installer.

### Troubleshooting

If you get an error message complaining about the lack of signature for this script, you can disable that security check with the following command inside PowerShell (as Administrator):

	set-executionpolicy -executionpolicy unrestricted

## Environment Variables

Note: this section applies for Jenkins jobs, but you can always use it to create custom Drive versions.

Each build can be driven by several envars.

If an envar is specifying a version, this means that the specified version of the library/software sources will be downloaded from the official website and compiled to fit Drive needs. It allows the creation of fully isolated and reproductible build environments.

__Important__: those values are given as example, if you want up-to-date ones, pick them from [tools/checksums.txt](https://github.com/nuxeo/nuxeo-drive/blob/master/tools/checksums.txt).

### Required Envars

- `PYTHON_DRIVE_VERSION` is the required **Python version** to use, i.e. `2.7.14`.
- `PYQT_VERSION` is the required **PyQt version** to use, i.e. `4.12.1`.
- `WORKSPACE` is the **absolute path to the WORKSPACE**, i.e. `/opt/jenkins/workspace/xxx`.
- `WORKSPACE_DRIVE` is the **absolute path to Drive sources**, i.e. `$WORKSPACE/sources`. If not defined, it will be set to `$WORKSPACE/sources` or `$WORKSPACE/nuxeo-drive` if folder exists else `$WORKSPACE`.

### Optional Envars

- `SIGNING_ID` is the certificate **authority name**.
- `SIP_VERSION` is the **SIP version** to use, i.e. `4.19.8`.
- `REPORT_PATH` is the absolute path to a directory where to store the generated report in case of failure, i.e. `$WORKSPACE`.
- `SPECIFIC_TEST` is a **specific test** to launch. The syntax must be the same as [pytest markers](http://doc.pytest.org/en/latest/example/markers.html#selecting-tests-based-on-their-node-id), i.e.:
```
    test_local_client.py (an entire test file)
    test_local_client.py::TestLocalClient (a whole class)
    test_local_client.py::TestLocalClient::test_make_documents (only one method)
```

#### GNU/Linux specific

- `COMPILE_WITH_DEBUG` to compile Python and Qt with debugging symbols. This variable cannot be null.

#### macOS Specific

Those are related to code-signing:
- `KEYCHAIN_PATH` is the **full path** to the certificate.
- `KEYCHAIN_PWD` is the **password** to unlock the certificate.

#### Windows specific

- `APP_NAME` is the **application name** used for code sign, i.e. `Nuxeo Drive`.
- `QT_PATH` is the **Qt path**, i.e. `C:\Qt\4.8.7`.
- `MINGW_PATH` is the **MinGW path** to use, i.e. `C:\mingw32`.
- `ISCC_PATH` is the **Inno Setup path** to use, i.e. `C:\Program Files (x86)\Inno Setup 5`.
- `SIGNTOOL_PATH` is the **SignTool path** to use, i.e. `C:\Program Files (x86)\Windows Kits\10\App Certification Kit`.
