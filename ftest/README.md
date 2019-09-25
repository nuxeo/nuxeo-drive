# Nuxeo Drive functional tests

Maven module to run the functional tests located in the [nxdrive.test](https://github.com/nuxeo/nuxeo-drive/tree/master/nxdrive/tests) Python module.

Uses the [ant-assembly-maven-plugin](https://github.com/nuxeo/ant-assembly-maven-plugin/) and [nuxeo-ftest](https://github.com/nuxeo/tools-nuxeo-ftest) resources to:

- Download the `nuxeo-drive` marketplace package from [Jenkins](http://qa.nuxeo.org/jenkins/view/Drive/) via the ``fetch-mp`` command of the [integration\_tests\_setup.py](https://github.com/nuxeo/nuxeo-drive/blob/master/tools/integration_tests_setup.py) script.

- Download a Nuxeo Server Tomcat distribution.

- Install the `nuxeo-drive` marketplace package.

- Start the Nuxeo server.

- Run the tests via the ``test`` command of the [integration\_tests\_setup.py](https://github.com/nuxeo/nuxeo-drive/blob/master/tools/integration_tests_setup.py) script:

  - Sets the environment variables needed by the tests: Nuxeo server URL and test user credentials.

  - Under Windows: extracts the MSI package expected to be built in the `dist` directory and run the tests from the extracted MSI package with `ndrive.exe test`.

  - Under Linux / OS X: runs the tests from sources with `nosetests -v -x`.

- Stop the Nuxeo server.

## Run tests with Maven

    mvn clean verify

If you are at the root of the [nuxeo-drive](https://github.com/nuxeo/nuxeo-drive/) repository, run:

    mvn clean verify -f ftest/pom.xml

You can use the `pgsql` profile to run the tests against a Nuxeo server connected to a PostgreSQL database:

    mvn clean verify -Ppgsql

## Run tests with Python

You need to have a running Nuxeo instance with the `nuxeo-drive` marketplace package installed or its bundles deployed.

Then at the root of the [nuxeo-drive](https://github.com/nuxeo/nuxeo-drive/) repository run:

    python tools/integration_tests_setup.py test
