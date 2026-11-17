import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mt5_readonly_mcp import guard, server
from mt5_readonly_mcp.guard import ConfigurationError, ReadOnlyViolation


def test_trading_functions_are_replaced(mt5):
    for name in ("order_send", "order_check"):
        with pytest.raises(ReadOnlyViolation):
            getattr(mt5, name)({"action": 1})
    assert "order_send" not in mt5.state.calls
    assert "order_check" not in mt5.state.calls


def test_missing_terminal_path_is_refused(monkeypatch):
    monkeypatch.delenv("MT5_TERMINAL_PATH")
    with pytest.raises(ConfigurationError, match="MT5_TERMINAL_PATH is not set"):
        guard.connect_and_guard()


def test_terminal_that_does_not_exist_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(tmp_path / "missing" / "terminal64.exe"))
    with pytest.raises(ConfigurationError, match="not found"):
        guard.connect_and_guard()


def test_connects_only_to_the_configured_terminal(mt5, environment):
    guard.connect_and_guard()
    assert mt5.state.calls[0] == ("initialize", str(environment / "terminal64.exe"))


def test_account_that_can_trade_is_refused_and_disconnected(mt5):
    mt5.state.account = mt5.make_account(trade_allowed=True)
    with pytest.raises(ReadOnlyViolation, match="fail-closed"):
        guard.connect_and_guard()
    assert mt5.state.calls[-1] == "shutdown"
    assert guard._state["connected"] is False


def test_investor_login_is_accepted(mt5):
    account = guard.connect_and_guard()
    assert account.trade_allowed is False


def test_failed_connection_is_reported(mt5):
    mt5.state.initialize_ok = False
    with pytest.raises(ConnectionError, match="investor password"):
        guard.connect_and_guard()


def test_guard_runs_on_every_tool_call(mt5, parse):
    assert parse(server.account_info())["read_only_verified"] is True
    # Someone logs the terminal in with the master password while the server runs.
    mt5.state.account = mt5.make_account(trade_allowed=True)
    with pytest.raises(ToolError, match="fail-closed"):
        server.positions()
