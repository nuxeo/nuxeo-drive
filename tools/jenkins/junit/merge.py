from pathlib import Path
from junitparser import JUnitXml, TestSuite

JUNIT_PATH = Path("tools/jenkins/junit/xml")


class JunitReport:
    def __init__(self, folder: Path = JUNIT_PATH, output: str = "junit.xml"):
        self.folder = folder
        self.output = output
        self.test_set = set()

    def add_tests(self, src: TestSuite) -> None:
        print(
            f"{src.tests} tests, "
            f"{src.skipped} skipped, "
            f"{src.failures} failures, "
            f"{src.errors} errors."
        )
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
        self.mainsuite = TestSuite("drive")

        self.process_xml(self.folder / "final.xml")

        for results in Path(self.folder).glob("**/test_*.xml"):
            self.process_xml(results)

        xml = JUnitXml()
        xml.add_testsuite(self.mainsuite)
        xml.write(self.folder / self.output)


if __name__ == "__main__":
    JunitReport().build()
