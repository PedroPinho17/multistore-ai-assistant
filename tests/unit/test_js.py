"""Corre os testes de JavaScript (tests/js, com o test runner do node) dentro do pytest.

Hoje: o check-lazy-chunks.mjs (Chart.js fora do arranque). Saltam se não houver node.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = sorted((Path(__file__).resolve().parents[1] / "js").glob("*.test.cjs"))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node não está instalado")
@pytest.mark.parametrize("path", JS_TESTS, ids=[p.name for p in JS_TESTS])
def test_javascript(path):
    run = subprocess.run([NODE, "--test", str(path)], capture_output=True, text=True, encoding="utf-8",
                         timeout=120)
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-2000:]


def test_there_are_javascript_tests():
    assert JS_TESTS, "tests/js sem ficheiros *.test.cjs"
