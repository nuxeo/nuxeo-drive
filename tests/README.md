# Nuxeo Drive Tests

You can customize several things using environment variables (see also [env.py](env.py)):

- `REPORT_PATH`: If set to an existing local folder, a ZIP'ed report will be created when a test failed.
- `SKIP_SENTRY`: Set to `1` to disable Sentry reports (enabled by default).
- `SENTRY_ENV`: The environment name to ease filtering on Sentry (default is `testing`).
- `SENTRY_DSN`: The Sentry DSN.
- `TEST_VOLUME`: [specific to `test_volume.py`] 3 comma-separated values:
  1. number of `folders`
  2. number of `files` to create inside each folder
  3. `depth`: the tree will be replicated into itself `depth` times
  - total is `???`
- `TEST_REMOTE_SCAN_VOLUME`: [specific to `test_volume.py`] Minimum number of documents to randomly import (default is `200,000`).
