"""
Unit tests for the Sync Service delta classifier
(:func:`nxdrive.alfresco.engine.watcher.sync_service.classify`).

These assert that real captured Sync Service payloads
(``tests/alfresco/sync_service/fixtures/delta_*.json``) are normalized into the
correct :class:`ChangeAction`. The classifier is pure (no Qt / DAO / network),
so these run without a live server or PySide6 — under ``pytest`` or as a plain
``python -m unittest`` module.
"""

import json
import unittest
from pathlib import Path

from nxdrive.alfresco.engine.watcher.sync_service import (
    KIND_CREATE,
    KIND_DELETE,
    KIND_MOVE,
    KIND_RENAME,
    KIND_UPDATE,
    classify,
)

FIXTURES = Path(__file__).resolve().parents[1] / "sync_service" / "fixtures"


def _load_changes(name: str) -> list:
    data = json.loads((FIXTURES / name).read_text())
    return data.get("changes", [])


def _only(name: str):
    changes = _load_changes(name)
    assert len(changes) == 1, f"{name}: expected exactly one change"
    return classify(changes[0])


class TestClassify(unittest.TestCase):
    def test_create_file(self) -> None:
        action = _only("delta_01_create_file.json")
        self.assertEqual(action.kind, KIND_CREATE)
        self.assertEqual(action.change_type, "CREATE_REPOS")
        self.assertTrue(action.node_id)
        self.assertFalse(action.is_folder)
        # Nearest parent is the first entry of parentNodeIds.
        self.assertEqual(action.new_parent_id, action.parent_node_ids[0])
        self.assertEqual(action.effective_name, action.name)

    def test_edit_content_carries_real_size(self) -> None:
        action = _only("delta_02_edit_content.json")
        self.assertEqual(action.kind, KIND_UPDATE)
        # Size is real only on content change (Phase 0 finding).
        self.assertGreater(action.size, 0)

    def test_rename_sets_to_name(self) -> None:
        action = _only("delta_03_rename.json")
        self.assertEqual(action.kind, KIND_RENAME)
        self.assertTrue(action.to_name)
        self.assertEqual(action.effective_name, action.to_name)

    def test_create_subfolder_is_folder(self) -> None:
        action = _only("delta_04_create_subfolder.json")
        self.assertEqual(action.kind, KIND_CREATE)

    def test_move_reparents(self) -> None:
        action = _only("delta_05_move.json")
        self.assertEqual(action.kind, KIND_MOVE)
        self.assertTrue(action.to_parent_node_ids)
        # After a move the effective parent is the new parent, not the old one.
        self.assertEqual(action.new_parent_id, action.to_parent_node_ids[0])
        self.assertNotEqual(action.parent_node_ids[0], action.to_parent_node_ids[0])
        self.assertTrue(action.to_path)

    def test_delete_is_tombstone(self) -> None:
        action = _only("delta_06_delete_file.json")
        self.assertEqual(action.kind, KIND_DELETE)
        # node_id is stable across the lifecycle and survives on the tombstone.
        self.assertTrue(action.node_id)

    def test_delete_folder(self) -> None:
        action = _only("delta_07_delete_folder.json")
        self.assertEqual(action.kind, KIND_DELETE)

    def test_seq_no_monotonic_across_matrix(self) -> None:
        """seqNo strictly increases across the captured event sequence."""
        ordered = [
            "delta_01_create_file.json",
            "delta_02_edit_content.json",
            "delta_03_rename.json",
            "delta_04_create_subfolder.json",
            "delta_05_move.json",
            "delta_06_delete_file.json",
            "delta_07_delete_folder.json",
        ]
        seqs = [_only(name).seq_no for name in ordered]
        self.assertTrue(all(s >= 0 for s in seqs))
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)), "seqNos must be unique")

    def test_baseline_and_noop_have_no_changes(self) -> None:
        self.assertEqual(_load_changes("delta_00_baseline.json"), [])
        self.assertEqual(_load_changes("delta_08_noop_after_drain.json"), [])

    def test_unknown_type_is_unknown_kind(self) -> None:
        action = classify({"type": "SOME_FUTURE_TYPE", "nodeId": "n1"})
        self.assertEqual(action.kind, "unknown")
        self.assertEqual(action.node_id, "n1")


if __name__ == "__main__":
    unittest.main()
