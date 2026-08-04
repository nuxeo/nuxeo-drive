"""Unit tests for nxdrive.drive.client.remote_protocol.

Verifies that ``RemoteClientProtocol`` is runtime-checkable and that
concrete classes are correctly classified by ``isinstance()``.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from nxdrive.drive.client.remote_protocol import RemoteClientProtocol
from nxdrive.drive.objects import RemoteFileInfo


class TestRemoteClientProtocolRuntimeCheckable:
    """RemoteClientProtocol must be decorated with @runtime_checkable."""

    def test_is_runtime_checkable(self):
        """The Protocol should support isinstance() checks."""
        # runtime_checkable protocols have __protocol_attrs__
        assert hasattr(RemoteClientProtocol, "__protocol_attrs__") or hasattr(
            RemoteClientProtocol, "__abstractmethods__"
        )

    def test_conforming_class_passes_isinstance(self):
        """A class implementing all required methods satisfies the check."""

        class _ConformingRemote:
            def get_filesystem_root_info(self) -> RemoteFileInfo:
                ...

            def get_fs_children(
                self, fs_item_id: str, /, *, filtered: bool = True
            ) -> List[RemoteFileInfo]:
                ...

            def get_fs_info(
                self, fs_item_id: str, /, *, parent_fs_item_id: str = None
            ) -> RemoteFileInfo:
                ...

            def get_info(
                self,
                ref: str,
                /,
                *,
                raise_if_missing: bool = True,
                parent_fs_item_id: str = None,
            ) -> Optional[RemoteFileInfo]:
                ...

            def fetch(
                self,
                ref: str,
                /,
                *,
                headers: Dict[str, str] = None,
                enrichers: List[str] = None,
            ) -> Dict[str, Any]:
                ...

            def stream_content(
                self,
                fs_item_id: str,
                file_path: Path,
                file_out: Path,
                /,
                **kwargs: Any,
            ) -> Path:
                ...

            def stream_file(
                self,
                parent_id: str,
                file_path: Path,
                /,
                *,
                filename: str = None,
                **kwargs: Any,
            ) -> RemoteFileInfo:
                ...

            def stream_update(
                self,
                fs_item_id: str,
                file_path: Path,
                /,
                *,
                parent_fs_item_id: str = None,
                filename: str = None,
            ) -> RemoteFileInfo:
                ...

            def make_folder(
                self, parent_id: str, name: str, /, *, overwrite: bool = False
            ) -> RemoteFileInfo:
                ...

            def delete(
                self, fs_item_id: str, /, *, parent_fs_item_id: str = None
            ) -> None:
                ...

            def rename(
                self, fs_item_id: str, new_name: str, /
            ) -> RemoteFileInfo:
                ...

            def move2(
                self, fs_item_id: str, parent_ref: str, name: str, /
            ) -> Dict[str, Any]:
                ...

        obj = _ConformingRemote()
        assert isinstance(obj, RemoteClientProtocol)

    def test_non_conforming_class_fails_isinstance(self):
        """A class missing required methods should NOT satisfy the check."""

        class _IncompleteRemote:
            def get_filesystem_root_info(self) -> RemoteFileInfo:
                ...

            # Missing all other methods

        obj = _IncompleteRemote()
        assert not isinstance(obj, RemoteClientProtocol)

    def test_plain_object_fails_isinstance(self):
        """A plain object should not satisfy the protocol."""
        assert not isinstance(object(), RemoteClientProtocol)
        assert not isinstance("string", RemoteClientProtocol)
        assert not isinstance(42, RemoteClientProtocol)
