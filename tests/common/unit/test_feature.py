"""Unit tests for nxdrive.drive.feature module."""

from types import SimpleNamespace
from unittest.mock import patch

from nxdrive.drive.feature import (
    DisabledFeatures,
    Feature,
    apply_server_type_restrictions,
)


class TestFeatureDefaults:
    def test_synchronization_disabled_by_default(self):
        assert Feature.synchronization is False

    def test_direct_edit_enabled_by_default(self):
        assert Feature.direct_edit is True

    def test_direct_transfer_enabled_by_default(self):
        assert Feature.direct_transfer is True

    def test_auto_update_disabled_by_default(self):
        assert Feature.auto_update is False


class TestApplyServerTypeRestrictions:
    def test_disables_features(self):
        mock_config = SimpleNamespace(disabled_features=["direct_edit", "s3"])
        with patch("nxdrive.drive.server_type.get", return_value=mock_config):
            # Save originals
            orig_de = Feature.direct_edit
            orig_s3 = Feature.s3
            try:
                apply_server_type_restrictions("TEST")
                assert Feature.direct_edit is False
                assert Feature.s3 is False
                assert "direct_edit" in DisabledFeatures
                assert "s3" in DisabledFeatures
            finally:
                # Restore
                Feature.direct_edit = orig_de
                Feature.s3 = orig_s3
                if "direct_edit" in DisabledFeatures:
                    DisabledFeatures.remove("direct_edit")
                if "s3" in DisabledFeatures:
                    DisabledFeatures.remove("s3")

    def test_no_disabled_features(self):
        mock_config = SimpleNamespace(disabled_features=[])
        with patch("nxdrive.drive.server_type.get", return_value=mock_config):
            apply_server_type_restrictions("EMPTY")
