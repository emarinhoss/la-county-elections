import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_analysis_functions():
    r = subprocess.run(["node", "tests/js/analysis.test.mjs"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent)
    assert r.returncode == 0, r.stderr
    assert "pass" in r.stdout
