#!/usr/bin/env python3
"""Tests for process-level runtime storage configuration."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RuntimeConfigurationTests(unittest.TestCase):
    def test_memory_and_qdrant_defaults_follow_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            memory_path = root / "memory.sqlite3"
            qdrant_path = root / "qdrant"
            environment = {
                **os.environ,
                "MEMORY_DB_PATH": str(memory_path),
                "QDRANT_PATH": str(qdrant_path),
            }
            script = (
                "import json; "
                "from graphrag.memory_store import DEFAULT_DB_PATH; "
                "from graphrag.vector_store import DEFAULT_QDRANT_PATH; "
                "print(json.dumps([str(DEFAULT_DB_PATH), str(DEFAULT_QDRANT_PATH)]))"
            )

            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parent.parent,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

            configured_paths = json.loads(completed.stdout)
            self.assertEqual(configured_paths, [str(memory_path), str(qdrant_path)])


if __name__ == "__main__":
    unittest.main()
