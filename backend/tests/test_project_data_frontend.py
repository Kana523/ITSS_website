from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("script", ["project-data", "blueprint-data", "schedule-data"])
def test_project_data_behaviour(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend behavior tests")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, "--test", f"tests/frontend/{script}.test.cjs"],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
