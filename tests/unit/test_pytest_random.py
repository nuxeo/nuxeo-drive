"""
Tests for pytests_random: a pytest plugin to mitigate random failures.
Adapted from github.com/pytest-dev/pytest-rerunfailures
"""
import pytest

pytest_plugins = "pytester"


@pytest.fixture(autouse=True)
def plugin(testdir):
    testdir.makeconftest("pytest_plugins = 'tests.pytest_random'")


def temporary_failure(count=1, reverse=False):
    comp = ">" if reverse else "<="
    return f"""
    import py
    path = py.path.local(__file__).dirpath().ensure('test.res')
    count = path.read() or 1
    path.write(int(count) + 1)
    if int(count) {comp} {count}:
        raise Exception('Failure: {{0}}'.format(count))
"""


def assert_outcomes(
    result, passed=1, skipped=0, failed=0, error=0, xfailed=0, xpassed=0, repeated=0
):
    outcomes = result.parseoutcomes()
    assert outcomes.get("passed", 0) == passed
    assert outcomes.get("skipped", 0) == skipped
    assert outcomes.get("failed", 0) == failed
    assert outcomes.get("error", 0) == error
    assert outcomes.get("xfailed", 0) == xfailed
    assert outcomes.get("xpassed", 0) == xpassed
    assert outcomes.get("repeated", 0) == repeated


def test_no_repeat_on_skipif_mark(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.skipif(reason='Skipping this test')
@pytest.mark.randombug('NXDRIVE-0', mode='STRICT')
def test_skip():
    pass
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, skipped=1)


def test_no_repeat_on_skip_call(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', mode='STRICT')
def test_skip():
    pytest.skip('Skipping this test')
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, skipped=1)


def test_no_repeat_on_xfail_mark(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.xfail()
@pytest.mark.randombug('NXDRIVE-0')
def test_xfail():
    assert False
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, xfailed=1)


def test_no_repeat_on_xfail_call(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0')
def test_xfail():
    pytest.xfail('Skipping this test')
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, xfailed=1)


def test_relax_on_failing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0')
def test_fail(): assert False
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1, repeated=9)


def test_relax_on_passing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0')
def test_success(): assert True
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result)


def test_relax_and_false_condition_on_failing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', condition=False)
def test_fail(): assert False
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1)


def test_relax_passing_after_failure(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0')
def test_fail():
"""
        + temporary_failure(3)
    )
    result = testdir.runpytest()
    assert_outcomes(result, repeated=3)


def test_strict_on_failing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', mode='STRICT')
def test_fail(): assert False
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1)


def test_strict_on_passing_test(testdir):
    """In STRICT mode, if the test never fails, the result _must_ be a failure."""
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', mode='STRICT')
def test_success(): assert True
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1, repeated=9)


def test_strict_and_false_condition_on_passing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', condition=False, mode='STRICT')
def test_success(): assert True
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result)


def test_strict_failing_after_success(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', mode='STRICT')
def test_fail():
"""
        + temporary_failure(3, reverse=True)
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1, repeated=3)


def test_strict_and_lower_repeat_number_on_passing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', repeat=5, mode='STRICT')
def test_success(): assert True
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1, repeated=4)


def test_bypass_on_passing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', mode='BYPASS')
def test_success(): assert True
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, skipped=1)


def test_bypass_on_failing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', mode='BYPASS')
def test_fail(): assert False
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, skipped=1)


def test_bypass_and_false_condition_on_passing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', condition=False, mode='BYPASS')
def test_success(): assert True
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result)


def test_bypass_and_false_condition_on_failing_test(testdir):
    testdir.makepyfile(
        """
import pytest
@pytest.mark.randombug('NXDRIVE-0', condition=False, mode='BYPASS')
def test_fail(): assert False
"""
    )
    result = testdir.runpytest()
    assert_outcomes(result, passed=0, failed=1)
