# Deployment Script

We are using scripts to automate the isolated environment creation. With only one script, you will be able to setup the environment, launch the tests suite and build the Drive package.

You could modify these scripts, but we will not be able to do support, these are the official way to manage the Drive ecosystem.

## GNU/Linux, macOS

### Usage

    sh tools/$OSI/deploy_ci_agent.sh [ARG]

Where `$OSI` is one of: `linux`, `osx`.

Possible `ARG`:

    --build: freeze the client into self-hosted binary package
    --check: check AppImage conformity (GNU/Linux only)
    --check-upgrade: check the auto-update works
    --install: install a complete development environment
    --install-python: install only Python
    --install-release: install a complete environment for a release (without tests requirements)
    --start: start Nuxeo Drive
    --tests: launch the tests suite

Executing the script without argument will setup/update the isolated environment.

### Dependencies:

See [pyenv](https://github.com/yyuu/pyenv/wiki/Common-build-problems#requirements) requirements.

## Windows

**PowerShell 5.1 or above** is required to run this script. You can find installation instructions [here](https://docs.microsoft.com/fr-fr/powershell/scripting/windows-powershell/wmf/setup/install-configure?view=powershell-7.1).

### Usage

    powershell .\tools\windows\deploy_ci_agent.ps1 [ARG] [-direct]

Possible `ARG`:

    -build: freeze the client into self-hosted binary package
    -check_upgrade: check the auto-update works
    -install: install a complete development environment
    -install_release: install a complete environment for a release (without tests requirements)
    -start: start Nuxeo Drive
    -tests: launch the tests suite

Executing the script without argument will setup.update the isolated environment.

### Dependencies:

[//]: # (XXX_PYTHON, XXX_INNO_SETUP)

- [Python 3.9.5](https://www.python.org/ftp/python/3.9.5/python-3.9.5.exe).
- [Inno Setup 6.1.2](http://www.jrsoftware.org/isdl.php) to create the installer.

### Troubleshooting

If you get an error message complaining about the lack of signature for this script, you can disable that security check with the following command inside PowerShell (as Administrator):

	set-executionpolicy -executionpolicy unrestricted

## Environment Variables

### Required Envars

- `WORKSPACE` is the **absolute path to the WORKSPACE**, i.e. `/opt/jenkins/workspace/xxx`.
- `WORKSPACE_DRIVE` is the **absolute path to Drive sources**, i.e. `$WORKSPACE/sources`. If not defined, it will be set to `$WORKSPACE/sources` or `$WORKSPACE/nuxeo-drive` if folder exists else `$WORKSPACE`.

### Optional Envars

- `PYTHON_DRIVE_VERSION` is the required **Python version** to use, i.e. `3.6.6`.
- `SIGNING_ID` is the certificate **authority name**.
- `REPORT_PATH` is the absolute path to a directory where to store the generated report in case of failure, i.e. `$WORKSPACE`.
- `ENABLE_CONVERTERS` to enable all **server converters**. Effective only when tests are ran using Maven.
- `SPECIFIC_TEST` is a **specific test** to launch. The syntax must be the same as [pytest markers](http://doc.pytest.org/en/latest/example/markers.html#selecting-tests-based-on-their-node-id), i.e.:
```
    test_local_client.py (an entire test file)
    test_local_client.py::TestLocalClient (a whole class)
    test_local_client.py::TestLocalClient::test_make_documents (only one method)
```
- `SKIP` is used to tweak tests checks:
```
    - SKIP=rerun to not rerun failed test(s)
```

#### MacOS Specific

Those are related to code-signing:
- `KEYCHAIN_PATH` is the **full path** to the certificate.
- `KEYCHAIN_PWD` is the **password** to unlock the certificate.

#### Windows specific

[//]: # (XXX_INNO_SETUP)

- `APP_NAME` is the **application name** used for code sign, i.e. `Nuxeo Drive`.
- `ISCC_PATH` is the **Inno Setup path** to use, i.e. `C:\Program Files (x86)\Inno Setup 6`.
- `PYTHON_DIR` is the **Python path** to use, i.e. `C:\Python377-32` (for Python 3.7.7).
- `SIGNTOOL_PATH` is the **SignTool path** to use, i.e. `C:\Program Files (x86)\Windows Kits\10\App Certification Kit`.
