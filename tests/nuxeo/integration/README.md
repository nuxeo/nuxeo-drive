# Integration Tests

## Building Nuxeo Drive

To build a version you can test, you have to use the standard way with a custom envar.
It will only freeze the application. If you need to test installers, just skip the envar setting.

On GNU/Linux:

```shell
export FREEZE_ONLY=1
./tools/linux/deploy_ci_agent.sh --build
```

On macOS:

```shell
export FREEZE_ONLY=1
./tools/osx/deploy_ci_agent.sh --build
```

On Windows:

```batch
set FREEZE_ONLY=1
powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -build
```

The resulting executable will be located at `dist/ndrive/ndrive[.exe]`.
