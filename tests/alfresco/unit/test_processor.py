"""Unit tests for :mod:`nxdrive.alfresco.engine.processor`.

The Alfresco processor subclasses the Drive processor and overrides
only a handful of behaviours (readonly handling, remote drift check,
Alfresco-specific rename). We mock the engine + DAO + local/remote
clients so we can exercise the overrides in isolation.
"""

from unittest.mock import Mock

import pytest

from nxdrive.alfresco.engine.processor import AlfrescoProcessor


@pytest.fixture
def mock_engine():
    """A mock ``AlfrescoEngine`` sufficient for constructor + method calls."""
    engine = Mock()
    engine.uid = "test-alfresco-uid"
    engine.dao = Mock()
    engine.local = Mock()
    engine.remote = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    engine.get_metadata_url = Mock(return_value="http://alfresco/metadata")
    engine.get_remote_url = Mock(return_value="http://alfresco/remote")
    return engine


@pytest.fixture
def processor(mock_engine) -> AlfrescoProcessor:
    """Construct an AlfrescoProcessor with mocked dependencies."""
    item_getter = Mock(return_value=None)
    return AlfrescoProcessor(mock_engine, item_getter)


class TestConstruction:
    def test_processor_holds_engine_reference(self, processor, mock_engine) -> None:
        assert processor.engine is mock_engine

    def test_processor_class_name(self, processor) -> None:
        assert processor.__class__.__name__ == "AlfrescoProcessor"


class TestGetNormalStateFromRemoteRef:
    def test_delegates_to_dao(self, processor, mock_engine) -> None:
        mock_engine.dao.get_normal_state_from_remote = Mock(return_value="doc-pair")
        got = processor._get_normal_state_from_remote_ref("abc-123")
        assert got == "doc-pair"
        mock_engine.dao.get_normal_state_from_remote.assert_called_once_with("abc-123")


class TestCheckPairState:
    """`check_pair_state` returns True when the pair should be processed."""

    def test_synchronized_pair_is_skipped(self) -> None:
        pair = Mock()
        pair.pair_state = "synchronized"
        assert AlfrescoProcessor.check_pair_state(pair) is False

    def test_unsynchronized_pair_is_skipped(self) -> None:
        pair = Mock()
        pair.pair_state = "unsynchronized"
        assert AlfrescoProcessor.check_pair_state(pair) is False

    def test_parent_prefixed_state_is_skipped(self) -> None:
        pair = Mock()
        pair.pair_state = "parent_updated"
        assert AlfrescoProcessor.check_pair_state(pair) is False

    def test_active_pair_is_processed(self) -> None:
        pair = Mock()
        pair.pair_state = "locally_created"
        assert AlfrescoProcessor.check_pair_state(pair) is True
