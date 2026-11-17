from mt5_readonly_mcp.__main__ import check


def test_check_passes_on_an_investor_login(capsys):
    assert check() == 0
    out = capsys.readouterr().out
    assert "read-only mode verified" in out
    assert "trade_allowed = False" in out


def test_check_fails_closed_on_an_account_that_can_trade(mt5, capsys):
    mt5.state.account = mt5.make_account(trade_allowed=True)
    assert check() == 1
    assert "FAILED: Refused (fail-closed)" in capsys.readouterr().out


def test_check_fails_without_configuration(monkeypatch, capsys):
    monkeypatch.delenv("MT5_TERMINAL_PATH")
    assert check() == 1
    assert "MT5_TERMINAL_PATH is not set" in capsys.readouterr().out
