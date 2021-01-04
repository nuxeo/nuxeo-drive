"""
(C) Copyright 2019-2021 Nuxeo (http://nuxeo.com/).

Usage: python merge.py FOLDER [FILE]

Merge JUnit reports from FOLDER into FILE.
FILE is optional and defaults to "junit.xml".

The final report will be saved into FOLDER/FILE.

It is possible to custom the test suite final report name
using the TEST_SUITE envar (default is "Project"), examples:
    export TEST_SUITE=Drive
    export TEST_SUITE=nxPyML

Contributors:
    Léa Klein
    Mickaël Schoentgen <mschoentgen@nuxeo.com>
"""
import os
import sys
from pathlib import Path

from junitparser import JUnitXml, TestSuite

__version__ = "1.0.0"


def print_suite(suite: TestSuite) -> None:
    print(
        f"{suite.name} suite: "
        f"{suite.tests} tests, "
        f"{suite.skipped} skipped, "
        f"{suite.failures} failures, "
        f"{suite.errors} errors."
    )


class JunitReport:
    def __init__(self, folder: str, output: str = "junit.xml"):
        self.folder = Path(folder)
        self.output = output
        self.test_set = set()

        if not self.folder.is_dir():
            err = f"The JUnit folder containing reports does not exist: {str(self.folder)!r}."
            raise FileNotFoundError(err)

    def add_tests(self, src: TestSuite) -> None:
        print_suite(src)
        for case in src:
            name = f"{case.classname}.{case.name}"
            if name not in self.test_set:
                self.mainsuite.add_testcase(case)
                self.test_set.add(name)

    def process_xml(self, path: Path) -> None:
        print(f"Processing {str(path)!r}")
        suites = JUnitXml.fromfile(path)
        if isinstance(suites, TestSuite):
            suites = [suites]
        for suite in suites:
            self.add_tests(suite)

    def build(self) -> None:
        test_suite = os.getenv("TEST_SUITE", "Project")
        self.mainsuite = TestSuite(test_suite)

        # Aggregate all reports in reverse order:
        # this is important for projects using "rerun" mechanism and where
        # reports are numbered so that report-2.xml should be processed
        # before report-1.xml in order to add successes before failures.
        for report in sorted(self.folder.glob("**/*.xml"), reverse=True):
            # Skip the final report, if present
            if report.name == self.output:
                continue
            self.process_xml(report)

        print("End of processing")
        print_suite(self.mainsuite)

        xml = JUnitXml()
        xml.add_testsuite(self.mainsuite)
        xml.write(self.folder / self.output)


if __name__ == "__main__":
    JunitReport(*sys.argv[1:]).build()
