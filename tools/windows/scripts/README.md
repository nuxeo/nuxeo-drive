# Windows Scripts

Everything used here is documented in details in [deployment.md](../../../docs/deployment.md).

Keep up-to-date:

- [envvars.bat](envvars.bat): Primary environment variables to control all other scripts.
- [setup.bat](setup.bat): Install/Update requirements.

Installer:

- [build.bat](build.bat): Build the application and its installer.

Launch:

- [launch.bat](launch.bat): Start the application from sources.

Test:

- [check-upgrade.bat](check-upgrade.bat): Test the auto-upgrade process. To do before any release.
- [tests.bat](tests.bat): Launch the complete tests suite.
- [tests-specific.bat](tests-specific.bat): Launch the tests suite on a specific test file/class/function.
- [tests-integration.bat](tests-integration.bat): Launch integration tests.
