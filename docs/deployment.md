# Explanations about deployment scripts

## GNU/Linux, macOS

### Usage

    sh tools/$OSI/deploy_jenkins_slave.sh [ARG]

Where `$OSI` is one of: `linux`, `osx`.

Possible `ARG`:

    --build: build the package
    --tests: launch the tests suite

### Dependencies:

See [pyenv](https://github.com/yyuu/pyenv/wiki/Common-build-problems#requirements) requirements.

## Windows

### Usage

    powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARG]

Possible `ARG`:

    -build: build the package
    -tests: launch the tests suite

### Dependencies:

You will need [Microsoft Visual C++ Compiler for Python 2.7](https://www.microsoft.com/en-us/download/details.aspx?id=44266) to build few required modules.

## Environment variables

Each build can be driven by several envars.

If an envar is specifying a version, this means that the specified version of the library/software sources will be downloaded from the official website and compiled to fit Drive needs. It allows to create full isolated and reproductible build environnements.

### Required envars

- `PYTHON_DRIVE_VERSION` is the required **Python version** to use, i.e. `2.7.13`.
- `PYQT_VERSION` is the required **PyQt version** to use, i.e. `4.12`.
- `WORKSPACE` is the **absolute path to the WORKSPACE**, i.e. `/opt/jenkins/workspace/xxx`.

### Optional envars

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
