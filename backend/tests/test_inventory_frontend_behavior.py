from pathlib import Path
from shutil import which
import subprocess

import pytest


def test_inventory_inputs_and_economics_rendering():
    node = which("node")
    if node is None:
        pytest.skip("Node.js is needed for frontend DOM unit tests")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("frontend_inventory_behavior.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
