import asyncio
import csv

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mt5_readonly_mcp import server
from mt5_readonly_mcp.export import export_path

READ_TOOLS = {"account_info", "positions", "pending_orders", "deal_history", "candles",
              "symbol_info", "symbols_list", "quotes"}
EXPORT_TOOLS = {"export_candles", "export_deals", "export_state"}


def test_server_exposes_exactly_the_documented_tools():
    tools = asyncio.run(server.server.list_tools())
    assert {tool.name for tool in tools} == READ_TOOLS | EXPORT_TOOLS
    for tool in tools:
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.read_only_hint is (tool.name in READ_TOOLS)


def test_suffixed_broker_symbols_are_resolved(mt5, parse):
    mt5.state.symbols = {"XAUUSDm": mt5.make_symbol("XAUUSDm", bid=4000.0, ask=4000.2)}
    assert parse(server.symbol_info("XAUUSD"))["symbol"] == "XAUUSDm"


def test_ambiguous_symbol_lists_candidates(mt5):
    mt5.state.symbols = {n: mt5.make_symbol(n) for n in ("XAUUSDm", "XAUUSDc")}
    with pytest.raises(ToolError, match="ambiguous"):
        server.symbol_info("XAUUSD")


def test_quotes_reports_bad_symbols_without_failing_the_batch(mt5, parse):
    mt5.state.symbols = {"BTCUSD": mt5.make_symbol("BTCUSD", bid=101.0, ask=101.5)}
    mt5.state.rates = {"BTCUSD": [{"time": 0, "open": 0, "high": 0, "low": 0, "close": 100.0,
                                   "tick_volume": 1, "spread": 0}] * 2}
    result = parse(server.quotes("BTCUSD, NOPE"))
    assert result["quotes"] == [["BTCUSD", 101.0, 101.5, 10, 1.0, 2]]
    assert result["errors"][0][0] == "NOPE"


def test_candles_rejects_unknown_timeframe(mt5):
    with pytest.raises(ToolError, match="timeframe must be one of"):
        server.candles("BTCUSD", "H2")


@pytest.mark.parametrize("out_dir", ["..", "../outside", "/tmp/elsewhere"])
def test_exports_cannot_leave_the_export_folder(out_dir):
    with pytest.raises(ValueError, match="inside the export folder"):
        export_path(out_dir, "history", "deals.csv")


def test_export_candles_writes_csv_inside_the_export_folder(mt5, parse, environment):
    mt5.state.symbols = {"US500": mt5.make_symbol("US500")}
    mt5.state.rates = {"US500": [{"time": 3600 * i, "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                                  "tick_volume": 10, "spread": 3} for i in range(5)]}
    result = parse(server.export_candles("US500", "H1,M15", count=3, out_dir="run1"))
    assert result["exported_files"] == 2
    path = environment / "exports" / "run1" / "candles" / "US500_H1.csv"
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][0] == "time" and len(rows) == 4
