from __future__ import annotations

import tempfile
import unittest
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

from labs.code_search import (
    FileRead,
    GrepResult,
    SymbolIndex,
    SyntaxErrorResult,
    WorkspaceError,
    find_definitions,
    grep_literal,
    read_file,
    read_range,
)


class CodeSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "pkg" / "primary.py").write_text(
            "def connect(url):\n    return url\n\nclass Client:\n    def connect(self):\n        return True\n",
            encoding="utf-8",
        )
        (self.root / "pkg" / "secondary.py").write_text(
            "def connect(url):\n    return url + '/secondary'\n", encoding="utf-8"
        )
        (self.root / "consumer.py").write_text(
            "from pkg.primary import connect as open_connection\n"
            "from pkg.primary import Client\n"
            "# connect appears in this comment, but is not a definition\n"
            "def run():\n"
            "    return open_connection('db')\n"
            "\n"
            "def outer():\n"
            "    def connect():\n"
            "        return None\n"
            "    return connect()\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_v0_reads_file_and_range(self) -> None:
        result = read_file(self.root, "consumer.py")
        self.assertIsInstance(result, FileRead)
        self.assertEqual(result.start_line, 1)
        self.assertIn("open_connection", result.text)
        self.assertEqual(read_range(self.root, "consumer.py", start_line=4, end_line=4).text, "def run():\n")
        (self.root / "large.txt").write_text("x" * 30000 + "\nlast\n", encoding="utf-8")
        self.assertEqual(read_range(self.root, "large.txt", start_line=2, end_line=2).text, "last\n")

    def test_v0_rejects_traversal_symlink_and_oversized_range(self) -> None:
        outside = self.root.parent / "outside-code.txt"
        outside.write_text("private", encoding="utf-8")
        link = self.root / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(WorkspaceError):
            read_file(self.root, "../outside-code.txt")
        with self.assertRaises(WorkspaceError):
            read_file(self.root, "link.txt")
        with self.assertRaises(WorkspaceError):
            read_file(self.root, "consumer.py", max_bytes=4)

    def test_v1_literal_search_and_no_match(self) -> None:
        result = grep_literal(self.root, "[E104]")
        self.assertIsInstance(result, GrepResult)
        self.assertEqual(result.status, "no_match")
        (self.root / "literal.txt").write_text("a[b]*\n", encoding="utf-8")
        self.assertEqual(grep_literal(self.root, "a[b]*").matches[0].text, "a[b]*")
        result = grep_literal(self.root, "connect")
        self.assertEqual(result.status, "matched")
        self.assertTrue(any(match.path == "consumer.py" and match.line == 3 for match in result.matches))

    def test_v1_timeout_is_distinct(self) -> None:
        result = grep_literal(self.root, "connect", timeout_seconds=0.000001)
        self.assertEqual(result.status, "timeout")

    def test_v2_finds_definitions_not_comments(self) -> None:
        result = find_definitions(self.root, "consumer.py", "connect")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].qualified_name, "outer.connect")
        self.assertEqual(result[0].line, 8)
        nested = find_definitions(self.root, "consumer.py", "outer")
        self.assertEqual(nested[0].end_line, 10)

    def test_v2_reports_syntax_error(self) -> None:
        bad = self.root / "bad.py"
        bad.write_text("def broken(:\n", encoding="utf-8")
        result = find_definitions(self.root, "bad.py")
        self.assertIsInstance(result, SyntaxErrorResult)
        self.assertEqual(result.line, 1)

    def test_v3_resolves_import_alias_and_exposes_candidates(self) -> None:
        index = SymbolIndex.build(self.root)
        aliases = index.references("connect", path="consumer.py")
        self.assertTrue(any(reference.resolution == "confirmed" for reference in aliases))
        self.assertEqual(index.find_symbols("connect")[0].name, "connect")
        candidates = index.find_symbols("connect")
        self.assertGreaterEqual(len(candidates), 3)
        self.assertEqual(index.syntax_errors, ())

    def test_v3_preserves_ambiguous_inference_and_unicode_positions(self) -> None:
        (self.root / "conditional.py").write_text(
            "def choose(flag):\n"
            "    if flag:\n"
            "        def connect(): return 1\n"
            "    else:\n"
            "        def connect(): return 2\n"
            "    return connect()\n"
            "\n"
            "def 连接(): return 1\n"
            "结果 = 连接()\n", encoding="utf-8"
        )
        index = SymbolIndex.build(self.root)
        ambiguous = index.references("connect", path="conditional.py")
        self.assertTrue(any(reference.resolution == "candidate" for reference in ambiguous))
        unicode_refs = index.references("连接", path="conditional.py")
        self.assertEqual(unicode_refs[0].resolution, "confirmed")

    def test_v3_keeps_dynamic_reference_unresolved(self) -> None:
        (self.root / "dynamic.py").write_text(
            "obj = get_object()\nobj.connect()\n", encoding="utf-8"
        )
        index = SymbolIndex.build(self.root)
        dynamic = index.references("connect", path="dynamic.py")
        self.assertTrue(any(reference.resolution == "unresolved" for reference in dynamic))

    def test_saved_checkpoints_are_independently_runnable(self) -> None:
        for version in range(4):
            checkpoint = importlib.import_module(f"labs.code_search.checkpoints.v{version}")
            self.assertEqual(checkpoint.read_range(self.root, "consumer.py", start_line=4, end_line=4).text,
                             "def run():\n")
            if version >= 1:
                self.assertEqual(checkpoint.grep_literal(self.root, "open_connection").status, "matched")
            if version >= 2:
                self.assertEqual(checkpoint.find_definitions(self.root, "consumer.py", "run")[0].name, "run")
            if version >= 3:
                self.assertTrue(checkpoint.SymbolIndex.build(self.root).find_symbols("run"))
            with tempfile.TemporaryDirectory() as replay:
                replay_root = Path(replay)
                source = Path("labs/code_search/checkpoints") / f"v{version}"
                shutil.copytree(source, replay_root / "code_search", ignore=shutil.ignore_patterns("__pycache__"))
                result = subprocess.run(
                    [sys.executable, "-c", "from code_search import read_file; print(read_file.__module__)"],
                    cwd=replay_root, capture_output=True, text=True, check=True,
                )
                self.assertEqual(result.stdout.strip(), "code_search.reader")


if __name__ == "__main__":
    unittest.main()
