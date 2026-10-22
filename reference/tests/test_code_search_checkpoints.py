from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CodeSearchCheckpointTest(unittest.TestCase):
    def test_saved_checkpoints_are_independently_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            (root / "consumer.py").write_text(
                "from pkg.primary import connect as open_connection\n"
                "from pkg.primary import Client\n"
                "# connect appears in this comment, but is not a definition\n"
                "def run():\n"
                "    return open_connection('db')\n",
                encoding="utf-8",
            )
            for version in range(4):
                checkpoint = importlib.import_module(f"labs.code_search.checkpoints.v{version}")
                self.assertEqual(checkpoint.read_range(root, "consumer.py", start_line=4, end_line=4).text,
                                 "def run():\n")
                if version >= 1:
                    self.assertEqual(checkpoint.grep_literal(root, "open_connection").status, "matched")
                if version >= 2:
                    self.assertEqual(checkpoint.find_definitions(root, "consumer.py", "run")[0].name, "run")
                if version >= 3:
                    self.assertTrue(checkpoint.SymbolIndex.build(root).find_symbols("run"))
                with tempfile.TemporaryDirectory() as replay:
                    replay_root = Path(replay)
                    source = Path(checkpoint.__file__).parent
                    shutil.copytree(source, replay_root / "code_search", ignore=shutil.ignore_patterns("__pycache__"))
                    result = subprocess.run(
                        [sys.executable, "-c", "from code_search import read_file; print(read_file.__module__)"],
                        cwd=replay_root, capture_output=True, text=True, check=True,
                    )
                    self.assertEqual(result.stdout.strip(), "code_search.reader")
