import pytest

try:
    from nxdrive.osi.windows import registry
except ImportError:
    pytestmark = pytest.mark.skip("Windows only.")


def test_registry_create():
    k = "Software\\Classes\\directory\\shell\\MockedApplicationName"
    try:
        registry.create(k)
        assert registry.exists(k)
    finally:
        assert registry.delete(k)


def test_registry_delete():
    k = "Software\\Classes\\directory\\shell\\MockedApplicationNameUnknown"
    assert registry.delete(k)


def test_registry_delete_value():
    k = "Software\\Classes\\directory\\shell\\MockedApplicationNameUnknown"
    v = "nonSenseValue"
    assert registry.delete_value(k, v)


def test_registry_exists():
    k = "Software\\Classes\\directory\\shell\\MockedApplicationNameUnknown"
    assert not registry.exists(k)


def test_registry_read():
    k = "Software\\MockedApplicationName"
    assert not registry.read(k)
    assert registry.delete(k)


def test_registry_write():
    k1 = "Software\\MockedApplicationName1"
    k2 = "Software\\MockedApplicationName2"
    values = {"a": "foo", "b": "42"}

    try:
        assert registry.write(k1, "bar")
        assert registry.write(k2, values)
        assert not registry.read(f"{k1}\\unknown")
        assert registry.read(k2) == values
    finally:
        assert registry.delete(k1)
        assert registry.delete(k2)
