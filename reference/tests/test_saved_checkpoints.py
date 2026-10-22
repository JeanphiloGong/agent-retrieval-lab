"""Replay supplied snapshots; learners need not create checkpoint packages."""

import importlib
from pathlib import Path
import tempfile
import unittest


TEXT = """# Manual
## Install
Install the client.
Use version 3.
## Appendix
### Limits
Version 3 is not supported in the free plan.
"""


class AccessCheckpointTests(unittest.TestCase):
    def test_standalone_version_checkpoints_replay_their_contracts(self):
        for version in range(4):
            module = importlib.import_module(f"labs.access.checkpoints.v{version}.control")
            if version == 0:
                identity = module.Identity("alice", "tenant-a")
                documents = [module.ProtectedDocument("a", "tenant-a", "release"),
                             module.ProtectedDocument("b", "tenant-b", "release")]
                self.assertEqual([doc.id for doc in module.visible_documents(identity, documents)], ["a"])
            else:
                identity = module.Identity("alice", "tenant-a", frozenset({"reader"}))
                documents = [module.ProtectedDocument("a", "tenant-a", "release", frozenset({"reader"})),
                             module.ProtectedDocument("f", "tenant-a", "finance", frozenset({"finance"}))]
                self.assertEqual([doc.id for doc in module.visible_documents(identity, documents)], ["a"])
            if version >= 2:
                cache = module.ScopedCache()
                cache.put(identity, "release", ["a"])
                self.assertEqual(cache.get(identity, "release"), ("a",))


class NavigationCheckpointTests(unittest.TestCase):
    def test_each_saved_checkpoint_replays_its_capability(self):
        for version in range(4):
            module = importlib.import_module(f"labs.navigation.checkpoints.v{version}.navigation")
            sections = module.document_tree(TEXT)
            self.assertEqual(sections[1].title, "Install")
            if version >= 1:
                self.assertEqual(module.find_sections(sections, "free plan")[0].title, "Limits")
            if version >= 2:
                self.assertTrue(module.read_range(TEXT, sections[0], max_lines=1).truncated)
            if version >= 3:
                self.assertEqual(len(module.combine_evidence({("manual", "v1"): TEXT},
                                                            ["install", "free plan"])), 2)


class OperationsCheckpointTests(unittest.TestCase):
    def test_standalone_version_checkpoints_replay_their_contracts(self):
        for version in range(5):
            module = importlib.import_module(f"labs.operations.checkpoints.v{version}.index")
            with tempfile.TemporaryDirectory() as directory:
                index = module.Index(Path(directory) / "index.db", "m1", "c1")
                index.apply("a", "doc", 1, "hello", [1, 0])
                self.assertEqual(index.generation("a"), (("doc", 1),))
                index.close()
            if version >= 2:
                self.assertTrue(hasattr(module, "QueryCache"))
            if version >= 3:
                serving = importlib.import_module(f"labs.operations.checkpoints.v{version}.serving")
                self.assertTrue(hasattr(serving, "WorkerPool"))
            if version >= 4:
                self.assertTrue(hasattr(serving, "report"))
