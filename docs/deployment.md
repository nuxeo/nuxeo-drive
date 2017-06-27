# Deployment Script

We are using scripts to automate the isolated environment creation. With only one script, you will be able to setup the environment, launch the tests suite and build Drive package. 

You could modify these scripts, but we will not be able to do support, these are the official way to manage the Drive ecosystem.

Finally, scripts names are refering to Jenkins, but you can always execute them on your personnal computer or outside a Jenkins job.

## GNU/Linux, macOS

### Usage

    sh tools/$OSI/deploy_jenkins_slave.sh [ARG]

Where `$OSI` is one of: `linux`, `osx`.

Possible `ARG`:

    --build: freeze the client into self-hosted binary package
    --start: start Nuxeo Drive
    --tests: launch the tests suite

Notes:
1. Executing the script without argument will setup the isolated environment.
2. For now, code signing is not implemented.

### Dependencies:

For both OSes, see [pyenv](https://github.com/yyuu/pyenv/wiki/Common-build-problems#requirements) requirements.

#### macOS

You will also need to install the Qt4 library, using HomeBrew:

	brew install qt4
	# if the previous command fails, try this one:
	brew install cartr/qt4/qt

#### GNU/Linux

You will also need to install the Qt4 qmake tool:

	apt install qt4-make

## Windows

### Usage

    powershell .\tools\windows\deploy_jenkins_slave.ps1 [ARG]

Possible `ARG`:

    -build: freeze the client into self-hosted binary package
    -start: start Nuxeo Drive
    -tests: launch the tests suite

Notes:
1. Executing the script without argument will setup the isolated environment.
2. For now, code signing is not implemented.

### Dependencies:

- [MinGW-w64](https://sourceforge.net/projects/mingw-w64/files/Toolchains%20targetting%20Win32/Personal%20Builds/mingw-builds/4.8.2/threads-posix/dwarf/i686-4.8.2-release-posix-dwarf-rt_v3-rev3.7z/download) installed into *C:\mingw32*;
- [Qt 4.8.7 open-source](https://download.qt.io/official_releases/qt/4.8/4.8.7/qt-opensource-windows-x86-mingw482-4.8.7.exe) installed into *C:\Qt\4.8.7*;
- [Microsoft Visual C++ Compiler for Python 2.7](https://www.microsoft.com/en-us/download/details.aspx?id=44266) to build few required modules.

### Troubleshooting

If you get an error message complaining about the lack of signature for this script.
You can disable that security check with the following command inside PowerShell:

	Set-ExecutionPolicy Unrestricted

## Environment Variables

Note: this section applies for Jenkins jobs, but you can always use it to create custom Drive versions.

Each build can be driven by several envars.

If an envar is specifying a version, this means that the specified version of the library/software sources will be downloaded from the official website and compiled to fit Drive needs. It allows to create full isolated and reproductible build environnements.

### Required Envars

- `PYTHON_DRIVE_VERSION` is the required **Python version** to use, i.e. `2.7.13`.
- `PYQT_VERSION` is the required **PyQt version** to use, i.e. `4.12`.
- `WORKSPACE` is the **absolute path to the WORKSPACE**, i.e. `/opt/jenkins/workspace/xxx`.

### Optional Envars

- `WORKSPACE_DRIVE` is the **absolute path to Drive sources**, i.e. `$WORKSPACE/sources`. If not defined, it will be set to `$WORKSPACE/sources` or `$WORKSPACE/nuxeo-drive` if folder exists else `$WORKSPACE`.
- `CXFREEZE_VERSION` is the **cx_Freeze version** to use, i.e. `4.3.3`.
- `SIP_VERSION` is the **SIP version** to use, i.e. `4.19`.
- `SPECIFIC_TEST` is a **specific test** to launch. The syntax must be the same as [pytest markers](http://doc.pytest.org/en/latest/example/markers.html#selecting-tests-based-on-their-node-id), i.e.:
```
    test_local_client.py (an entire test file)
    test_local_client.py::TestLocalClient (a whole class)
    test_local_client.py::TestLocalClient::test_make_documents (only one method)
```
- `REPORT_PATH` is the absolute path to a directory where to store the generated report in case of failure, i.e. `$WORKSPACE`.
