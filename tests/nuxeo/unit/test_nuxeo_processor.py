"""Unit tests for nxdrive.nuxeo.engine.processor module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.drive.exceptions import PairInterrupt


class TestProcessorCheckPairState:
    def test_synchronized_excluded(self):
        from nxdrive.nuxeo.engine.processor import Processor

        pair = Mock()
        pair.pair_state = "synchronized"
        pair.remote_state = ""
        assert Processor.check_pair_state(pair) is False

    def test_unsynchronized_excluded(self):
        from nxdrive.nuxeo.engine.processor import Processor

        pair = Mock()
        pair.pair_state = "unsynchronized"
        pair.remote_state = ""
        assert Processor.check_pair_state(pair) is False

    def test_parent_prefix_excluded(self):
        from nxdrive.nuxeo.engine.processor import Processor

        pair = Mock()
        pair.pair_state = "parent_created"
        pair.remote_state = ""
        assert Processor.check_pair_state(pair) is False

    def test_remote_todo_excluded(self):
        from nxdrive.nuxeo.engine.processor import Processor

        pair = Mock()
        pair.pair_state = "locally_modified"
        pair.remote_state = "todo"
        assert Processor.check_pair_state(pair) is False

    def test_valid_state_included(self):
        from nxdrive.nuxeo.engine.processor import Processor

        pair = Mock()
        pair.pair_state = "locally_modified"
        pair.remote_state = "modified"
        assert Processor.check_pair_state(pair) is True


class TestProcessorDigestStatus:
    def test_folderish_returns_ok(self):
        from nxdrive.nuxeo.engine.processor import Processor
        from nxdrive.drive.constants import DigestStatus

        pair = Mock()
        pair.folderish = True
        pair.pair_state = "remotely_created"
        pair.remote_digest = None
        assert Processor._digest_status(pair) is DigestStatus.OK

    def test_non_remotely_created_returns_ok(self):
        from nxdrive.nuxeo.engine.processor import Processor
        from nxdrive.drive.constants import DigestStatus

        pair = Mock()
        pair.folderish = False
        pair.pair_state = "locally_modified"
        pair.remote_digest = "abc123"
        assert Processor._digest_status(pair) is DigestStatus.OK

    def test_remotely_created_file_checks_digest(self):
        from nxdrive.nuxeo.engine.processor import Processor
        from nxdrive.drive.constants import DigestStatus

        pair = Mock()
        pair.folderish = False
        pair.pair_state = "remotely_created"
        pair.remote_digest = "a" * 32  # Valid MD5 length
        result = Processor._digest_status(pair)
        assert result is DigestStatus.OK


class TestProcessorSoftLocks:
    def _make_processor(self):
        from nxdrive.nuxeo.engine.processor import Processor

        with patch.object(Processor, "__init__", return_value=None):
            proc = Processor.__new__(Processor)
        proc.engine = Mock()
        proc.engine.uid = "eng-1"
        Processor.soft_locks = {}
        return proc

    def test_lock_soft_path(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = self._make_processor()
        result = proc._lock_soft_path(Path("/tmp/Test.txt"))
        assert result == Path("/tmp/test.txt")
        assert Path("/tmp/test.txt") in Processor.soft_locks["eng-1"]

    def test_lock_already_locked_raises(self):
        proc = self._make_processor()
        proc._lock_soft_path(Path("/tmp/Test.txt"))
        with pytest.raises(PairInterrupt):
            proc._lock_soft_path(Path("/tmp/test.txt"))

    def test_unlock_soft_path(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = self._make_processor()
        proc._lock_soft_path(Path("/tmp/Test.txt"))
        proc._unlock_soft_path(Path("/tmp/Test.txt"))
        assert Path("/tmp/test.txt") not in Processor.soft_locks.get("eng-1", {})


class TestProcessorReadonlyLocks:
    def _make_processor(self):
        from nxdrive.nuxeo.engine.processor import Processor

        with patch.object(Processor, "__init__", return_value=None):
            proc = Processor.__new__(Processor)
        proc.engine = Mock()
        proc.engine.uid = "eng-1"
        proc.local = Mock()
        Processor.readonly_locks = {}
        return proc

    def test_unlock_readonly_new_path(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = self._make_processor()
        proc.local.unlock_ref.return_value = 0o644
        proc._unlock_readonly(Path("/tmp/file.txt"))
        assert Path("/tmp/file.txt") in Processor.readonly_locks["eng-1"]
        count, lock = Processor.readonly_locks["eng-1"][Path("/tmp/file.txt")]
        assert count == 1
        assert lock == 0o644

    def test_unlock_readonly_existing_increments(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = self._make_processor()
        Processor.readonly_locks["eng-1"] = {Path("/tmp/file.txt"): [1, 0o644]}
        proc._unlock_readonly(Path("/tmp/file.txt"))
        count, lock = Processor.readonly_locks["eng-1"][Path("/tmp/file.txt")]
        assert count == 2

    def test_lock_readonly_decrements_and_relocks(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = self._make_processor()
        Processor.readonly_locks["eng-1"] = {Path("/tmp/file.txt"): [1, 0o644]}
        proc._lock_readonly(Path("/tmp/file.txt"))
        # After decrement to 0, path should be removed and relocked
        assert Path("/tmp/file.txt") not in Processor.readonly_locks["eng-1"]
        proc.local.lock_ref.assert_called_once_with(Path("/tmp/file.txt"), 0o644)

    def test_lock_readonly_missing_path_returns(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = self._make_processor()
        Processor.readonly_locks["eng-1"] = {}
        # Should not raise
        proc._lock_readonly(Path("/tmp/nonexistent.txt"))
