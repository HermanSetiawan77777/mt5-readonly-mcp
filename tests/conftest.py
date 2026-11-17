import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import fake_metatrader5  # noqa: E402

# Must happen before the package is imported anywhere.
sys.modules["MetaTrader5"] = fake_metatrader5

from mt5_readonly_mcp import guard  # noqa: E402


@pytest.fixture
def mt5():
    return fake_metatrader5


@pytest.fixture(autouse=True)
def environment(tmp_path, monkeypatch):
    """A fresh fake terminal, a dedicated terminal path and an export folder per test."""
    fake_metatrader5.state.reset()
    guard._state["connected"] = False
    terminal = tmp_path / "terminal64.exe"
    terminal.write_bytes(b"")
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(terminal))
    monkeypatch.setenv("MT5_EXPORT_DIR", str(tmp_path / "exports"))
    return tmp_path


@pytest.fixture
def parse():
    return json.loads
