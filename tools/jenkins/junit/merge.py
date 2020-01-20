from pathlib import Path

from junitparser import JUnitXml, TestSuite

JUNIT_PATH = Path("tools/jenkins/junit/xml")


def print_suite(suite: TestSuite) -> None:
    print(
        f"{suite.name} suite: "
        f"{suite.tests} tests, "
        f"{suite.skipped} skipped, "
        f"{suite.failures} failures, "
        f"{suite.errors} errors."
    )


class JunitReport:
    def __init__(self, folder: Path = JUNIT_PATH, output: str = "junit.xml"):
        self.folder = folder
        self.output = output
        self.test_set = set()

    def add_tests(self, src: TestSuite) -> None:
        print_suite(src)
        for case in src:
            name = f"{case.classname}.{case.name}"
            if name not in self.test_set:
                self.mainsuite.add_testcase(case)
                self.test_set.add(name)

    def process_xml(self, path: Path) -> None:
        if not path.exists():
            return
        print(f"Processing {path}")
        suites = JUnitXml.fromfile(path)
        if isinstance(suites, TestSuite):
            suites = [suites]
        for suite in suites:
            self.add_tests(suite)

    def build(self) -> None:
        self.mainsuite = TestSuite("Drive")

        self.process_xml(self.folder / "final.xml")

        for idx in (2, 1):
            # First add the results from the reruns (suffixed with "2")
            # then the first runs, to add successes before failures.
            for results in Path(self.folder).glob(f"**/*.{idx}.xml"):
                self.process_xml(results)

        print("End of processing")
        print_suite(self.mainsuite)

        xml = JUnitXml()
        xml.add_testsuite(self.mainsuite)
        xml.write(self.folder / self.output)


if __name__ == "__main__":
    JunitReport().build()
