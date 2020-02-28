# Nuxeo Drive Tests

## Run

### No Server Required

Part of the tests are managed by `tox`, to run all:
```bash
tox
```

To run a specific test environment, check the current list using:
```bash
tox -l
```

And then run the desired environment:
```bash
TOXENV=unit tox
```

You can select what test to run using the `-k` selector (see [Using -k expr to select tests based on their name](http://doc.pytest.org/en/latest/example/markers.html#using-k-expr-to-select-tests-based-on-their-name) for details):
```bash
TOXENV=unit tox -- -k url
TOXENV=unit tox -- -k test_utils
TOXENV=unit tox -- -k test_utils.py
```

### Server Required

The other part of tests is managed by the deploy script. Check the [documentation](../docs/deployment.md).

## Envars

You can customize several things using environment variables (see also [env.py](env.py)):

- `DOCTYPE_FILE`: Document type for file creation (default is `File`).
- `DOCTYPE_FOLDERISH`: Document type for non-file creations (default is `Folder`).
- `REPORT_PATH`: If set to an existing local folder, a ZIP'ed report will be created when a test failed.
- `SKIP_SENTRY`: Set to `1` to disable Sentry reports (enabled by default).
- `SENTRY_DSN`: The Sentry DSN.
- `TEST_VOLUME`: [specific to `test_volume.py`] 3 comma-separated values:
  1. number of `folders`
  2. number of `files` to create inside each folder
  3. `depth`: the tree will be replicated into itself `depth` times
  - total is `???`
- `TEST_REMOTE_SCAN_VOLUME`: [specific to `test_volume.py`] Minimum number of documents to randomly import (default is `200,000`).
