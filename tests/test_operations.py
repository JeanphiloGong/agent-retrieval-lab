import asyncio
import importlib
from pathlib import Path
import tempfile
import unittest

from labs.access.control import Identity
from labs.operations.index import Index, QueryCache
from labs.operations.serving import Overloaded, Sample, WorkerPool, report


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "index.db"
        self.index = Index(self.path, "m1", "c1")
        self.identity = Identity("alice", "a")

    def tearDown(self):
        self.index.close()
        self.temp.cleanup()

    def test_restart_and_configuration_guard(self):
        self.index.apply("a", "doc", 1, "hello", [1, 0])
        self.index.close()
        self.index = Index(self.path, "m1", "c1")
        self.assertEqual(self.index.search(self.identity, [1, 0])[0].document.id, "doc")
        with self.assertRaises(ValueError):
            Index(self.path, "m2", "c1")

    def test_duplicate_and_out_of_order_delete(self):
        self.assertTrue(self.index.apply("a", "doc", 1, "hello", [1, 0]))
        self.assertFalse(self.index.apply("a", "doc", 1, "hello", [1, 0]))
        self.index.apply("a", "doc", 3, None)
        self.assertFalse(self.index.apply("a", "doc", 2, "old", [1, 0]))
        self.assertEqual(self.index.search(self.identity, [1, 0]), [])

    def test_conflicting_same_revision_rejected(self):
        self.index.apply("a", "doc", 1, "hello", [1, 0])
        with self.assertRaises(ValueError):
            self.index.apply("a", "doc", 1, "different", [1, 0])

    def test_tenant_scope(self):
        self.index.apply("b", "private", 1, "secret", [1, 0])
        self.assertEqual(self.index.search(self.identity, [1, 0]), [])

    def test_cache_update_and_subject_scope(self):
        cache = QueryCache(1)
        compute = lambda: ["value"]
        self.assertFalse(cache.query(self.identity, (), "q", compute)[1])
        self.assertTrue(cache.query(self.identity, (), "q", compute)[1])
        self.assertFalse(cache.query(self.identity, (("doc", 2),), "q", compute)[1])
        self.assertFalse(cache.query(Identity("bob", "a"), (), "q", compute)[1])
        self.assertEqual(len(cache.entries), 1)

    def test_report_preserves_failure_denominator(self):
        data = report([Sample(.1, True), Sample(.5, False, True)], 1, environment={"cache": "cold"})
        self.assertEqual(data["quality"], .5)
        self.assertEqual(data["failure_rate"], .5)
        self.assertEqual(data["p95"], .5)

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


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_overload_and_cancel_release_worker(self):
        pool = WorkerPool(1, 1)
        started = asyncio.Event()
        gate = asyncio.Event()
        async def block():
            started.set()
            await gate.wait()
            return 1
        first = asyncio.create_task(pool.submit(block))
        await started.wait()
        second = asyncio.create_task(pool.submit(block))
        await asyncio.sleep(0)
        with self.assertRaises(Overloaded):
            await pool.submit(block)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        gate.set()
        self.assertEqual(await second, 1)
        await pool.close()

    async def test_failures_dont_kill_worker(self):
        pool = WorkerPool(1, 1)
        async def fail():
            raise ValueError("injected")
        with self.assertRaises(ValueError):
            await pool.submit(fail)
        async def success():
            return 7
        self.assertEqual(await pool.submit(success), 7)
        await pool.close()
