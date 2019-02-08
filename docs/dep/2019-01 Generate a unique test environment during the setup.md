# Generate a unique test environment during the setup

- Created: 2019-01-31
- Last-Modified: YYYY-MM-DD
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>,
          Léa Klein <lklein@uxeo.com>
- Status: draft
- Related-Ticket: [NXDRIVE-1436](https://jira.nuxeo.com/browse/NXDRIVE-1436)

## Abstract

Generate a test environment that will be unique to the run time.
Running the test suite twice should not use same users and workspaces to ensure tests reproductilibity, reliability and debugging.

## Rationale

As of now, tests are calling the `NuxeoDrive.SetupIntegrationTests` operation to create users and workspaces.

With the future move to OpenShift for testing ([NXDRIVE-1435](https://jira.nuxeo.com/browse/NXDRIVE-1435)), we will encounter errors because 3 OSes will talk to the server at the same time.
It will break everything as users and workspaces are the same everywhere.

Before that move to OpenShift, we need to tweak tests setup to:

- create needed user for each tests;
- create the workspace based on the OS name and the test name/function/whatever (we should keep it short for OS path limits);
- enable synchronization of that workspace for users that need it;
- clean-up everything at the end of the test.

### Idea

Using the Python client, we should be able to create what we need.
We should no more call the `NuxeoDrive.SetupIntegrationTests` operation.

## Specifications

We will completely move to `pytest` instead of having a mix with `unittest` format.
We then may be able to fully embrace pytest [fixture's factories](https://docs.pytest.org/en/latest/fixture.html#factories-as-fixtures).
Speaking of factories, we may have a look at [Factory Boy](https://factoryboy.readthedocs.io/en/latest/).

We will split the `tests` folder to reflect the actual tests file it constains.
I am thinking of somthing like:

```tree
tests/
    - conftest.py (global fixtures)
    - /functional
        - conftest.py (Nuxeo specific fixtures)
        - conftest.py
        - test_local_creations.py
        - test_synchronization.py
    - integration
        - ??? (for the future)
    - unit
        - conftest.py (maybe unecessary)
        - test_report.py
        - tet_utils.py
```

Where:

- `tests/functional` are tests that require a Nuxeo instance to work with.
- `test/integration` will be the folder where real scenarii will be tested.
- `test/unit` are real unit tests, with no requirements but the Nuxeo Drive code.

It will speed tests because only `tests/functional` will require a server connection and it will help future parallelization.

## Notes

TODO?
