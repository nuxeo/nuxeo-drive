import pytest

try:
    from nxdrive.drive.constants import CONFIG_REGISTRY_KEY
    from nxdrive.drive.osi.windows import registry
except ImportError:
    pytestmark = pytest.mark.skip("Windows only.")


def test_registry_configuration(request, manager_factory):
    """Test the configuration stored in the registry."""

    with manager_factory(with_engine=False) as manager:
        osi = manager.osi
        key = CONFIG_REGISTRY_KEY

        assert not osi.get_system_configuration()

        def cleanup():
            registry.delete_value(key, "update-site-url")
            registry.delete_value(key, "channel")

        request.addfinalizer(cleanup)

        # Add new parameters
        registry.write(key, {"update-site-url": "http://no.where"})
        registry.write(key, {"ChAnnEL": "beta"})

        conf = osi.get_system_configuration()
        assert conf["update_site_url"] == "http://no.where"
        assert conf["channel"] == "beta"
