"""MCP tools. Every tool reads from MetaTrader 5; none can place, modify or close orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import MetaTrader5 as mt5
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .data import (
    ACCOUNT_TYPE,
    CANDLE_COLUMNS,
    ORDER_STATE,
    ORDER_TYPE,
    TIME_BASIS,
    TIMEFRAMES,
    candle_rows,
    closed_trades,
    resolve_symbol,
    rnd,
    split_list,
    ts,
)
from .export import export_path, safe_name, write_csv
from .guard import connect_and_guard, lock

# Tools that only read: they change nothing on the account or on disk.
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                       idempotent_hint=True, open_world_hint=False)
# Export tools also only read the account, but write CSV files inside MT5_EXPORT_DIR.
EXPORT = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                         idempotent_hint=True, open_world_hint=False)

server = MCPServer(
    "mt5-readonly",
    version=__version__,
    instructions=(
        "Read-only access to the user's MetaTrader 5 account (investor-password login). "
        "There is no way to place, modify or close orders. All times are broker server time. "
        "For history analysis, call deal_history, or export_deals for large ranges."
    ),
)


def run_read(work) -> str:
    """Run a read under the lock and the read-only guard; return compact JSON."""
    try:
        with lock:
            connect_and_guard()
            result = work()
    except Exception as exc:  # noqa: BLE001 - every failure is reported to the client
        raise ToolError(str(exc)) from exc
    return json.dumps(result, separators=(",", ":"), ensure_ascii=False)


def _position_row(p) -> list:
    return [p.ticket, p.symbol, "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
            p.volume, rnd(p.price_open), rnd(p.sl), rnd(p.tp), rnd(p.price_current),
            round(p.profit, 2), round(p.swap, 2), ts(p.time), p.comment]


POSITION_COLUMNS = ["ticket", "symbol", "side", "lots", "open_price", "sl", "tp",
                    "current_price", "profit", "swap", "open_time", "comment"]


@server.tool(annotations=READ)
def account_info() -> str:
    """Account summary: balance, equity, margin, leverage, account type (DEMO/REAL)
    and read-only status (trade_allowed must be false)."""
    def work():
        a = mt5.account_info()
        return {
            "login": a.login, "server": a.server, "company": a.company,
            "account_type": ACCOUNT_TYPE.get(a.trade_mode, str(a.trade_mode)),
            "currency": a.currency, "balance": a.balance, "equity": a.equity,
            "floating_profit": a.profit, "margin": a.margin,
            "margin_free": a.margin_free, "margin_level_pct": a.margin_level,
            "leverage": a.leverage, "trade_allowed": a.trade_allowed,
            "read_only_verified": not a.trade_allowed,
        }
    return run_read(work)


@server.tool(annotations=READ)
def positions(symbol: str | None = None) -> str:
    """Open positions. symbol is optional and matches partially ('XAUUSD' matches 'XAUUSDm')."""
    def work():
        rows = [_position_row(p) for p in (mt5.positions_get() or ())
                if not symbol or symbol.upper() in p.symbol.upper()]
        return {"time_basis": TIME_BASIS, "count": len(rows),
                "columns": POSITION_COLUMNS, "positions": rows}
    return run_read(work)


@server.tool(annotations=READ)
def pending_orders(symbol: str | None = None) -> str:
    """Active pending orders (limit, stop and stop-limit). Open positions are in positions().
    symbol is optional and matches partially."""
    def work():
        rows = []
        for o in mt5.orders_get() or ():
            if symbol and symbol.upper() not in o.symbol.upper():
                continue
            tick = mt5.symbol_info_tick(o.symbol)
            rows.append([
                o.ticket, o.symbol, ORDER_TYPE.get(o.type, str(o.type)),
                round(o.volume_current, 2), rnd(o.price_open), rnd(o.sl), rnd(o.tp),
                rnd(tick.bid) if tick else 0.0, ts(o.time_setup),
                ts(o.time_expiration) if o.time_expiration else "",
                ORDER_STATE.get(o.state, str(o.state)), o.comment,
            ])
        return {
            "time_basis": TIME_BASIS, "count": len(rows),
            "columns": ["ticket", "symbol", "type", "lots", "entry_price", "sl", "tp",
                        "current_bid", "setup_time", "expiration", "state", "comment"],
            "orders": rows,
        }
    return run_read(work)


@server.tool(annotations=READ)
def deal_history(date_from: str, date_to: str | None = None,
                 symbol: str | None = None, max_trades: int = 300) -> str:
    """Closed trades, one row per position (entry and exit merged).
    date_from/date_to are YYYY-MM-DD (empty date_to = until now). symbol is optional.
    max_trades is capped at 1000, newest first kept. Columns include side, lots,
    open/close price, initial SL/TP, exit reason (STOP_LOSS, TAKE_PROFIT, MANUAL_*,
    STOP_OUT), profit, commission, swap and net. For long histories use export_deals()."""
    return run_read(lambda: closed_trades(date_from, date_to, symbol, min(int(max_trades), 1000)))


@server.tool(annotations=READ)
def candles(symbol: str, timeframe: str = "H1", count: int = 200) -> str:
    """OHLC candles from the broker. timeframe: M1 M5 M15 M30 H1 H4 D1 W1 MN1.
    count is capped at 1000. The last candle is usually still open."""
    def work():
        tf = timeframe.strip().upper()
        if tf not in TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {list(TIMEFRAMES)}")
        n = max(1, min(int(count), 1000))
        sym = resolve_symbol(symbol)
        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, TIMEFRAMES[tf], 0, n)
        if rates is None:
            raise RuntimeError(f"Could not read candles for {sym} {tf}: {mt5.last_error()}")
        rows = candle_rows(rates)
        return {"symbol": sym, "timeframe": tf, "time_basis": TIME_BASIS, "count": len(rows),
                "last_candle_may_be_open": True, "columns": CANDLE_COLUMNS, "candles": rows}
    return run_read(work)


@server.tool(annotations=READ)
def symbol_info(symbol: str) -> str:
    """Symbol specification: digits, contract size, min/max/step volume,
    tick value, current bid/ask and spread, swaps."""
    def work():
        sym = resolve_symbol(symbol)
        mt5.symbol_select(sym, True)
        s = mt5.symbol_info(sym)
        return {
            "symbol": s.name, "description": s.description, "digits": s.digits,
            "point": s.point, "contract_size": s.trade_contract_size,
            "volume_min": s.volume_min, "volume_max": s.volume_max,
            "volume_step": s.volume_step, "tick_size": s.trade_tick_size,
            "tick_value": s.trade_tick_value, "profit_currency": s.currency_profit,
            "bid": s.bid, "ask": s.ask, "spread_points": s.spread,
            "swap_long": s.swap_long, "swap_short": s.swap_short,
        }
    return run_read(work)


@server.tool(annotations=READ)
def symbols_list(pattern: str = "", max_results: int = 400, tradable_only: bool = True) -> str:
    """Symbols offered by the broker. pattern uses MetaTrader 5 wildcards, e.g. '*XAU*'
    or 'EUR*'; empty = all. Returns name, category path, digits, spread, min volume
    and contract size, so symbol names never have to be guessed."""
    def work():
        pat = pattern.strip() or "*"
        rows = [[s.name, s.path, s.digits, s.spread, s.volume_min, s.trade_contract_size]
                for s in (mt5.symbols_get(pat) or ())
                if not (tradable_only and s.trade_mode == 0)]  # 0 = trading disabled
        rows.sort(key=lambda r: r[1])
        limit = max(1, min(int(max_results), 2000))
        return {"pattern": pat, "total_matched": len(rows), "returned": min(len(rows), limit),
                "columns": ["symbol", "category_path", "digits", "spread_points",
                            "volume_min", "contract_size"],
                "symbols": rows[:limit]}
    return run_read(work)


@server.tool(annotations=READ)
def quotes(symbols: str) -> str:
    """Price snapshot for many symbols in one call, comma-separated, e.g. 'XAUUSD,BTCUSD,US500'.
    Includes spread and change versus the previous daily close. Max 60 symbols."""
    def work():
        rows, errors = [], []
        for raw in split_list(symbols)[:60]:
            try:
                sym = resolve_symbol(raw)
                mt5.symbol_select(sym, True)
                s = mt5.symbol_info(sym)
                d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 2)
                change = 0.0
                if d1 is not None and len(d1) == 2 and d1[0]["close"]:
                    change = (s.bid - d1[0]["close"]) / d1[0]["close"] * 100
                rows.append([sym, rnd(s.bid), rnd(s.ask), s.spread, round(change, 2), s.digits])
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not fail the batch
                errors.append([raw, str(exc)[:120]])
        return {"count": len(rows),
                "columns": ["symbol", "bid", "ask", "spread_points", "day_change_pct", "digits"],
                "quotes": rows, "errors": errors}
    return run_read(work)


@server.tool(annotations=EXPORT)
def export_candles(symbols: str, timeframes: str = "H1", count: int = 1000, out_dir: str = "") -> str:
    """Write OHLC candles to CSV files instead of the conversation, for analysing many
    symbols. symbols and timeframes are comma-separated ('XAUUSD,BTCUSD' / 'M15,H1').
    Files: <export folder>/<out_dir>/candles/<SYMBOL>_<TF>.csv, overwritten on each export.
    out_dir is an optional subfolder. Max 200 files and 100,000 candles per file."""
    def work():
        syms, tfs = split_list(symbols), [t.upper() for t in split_list(timeframes)]
        if not syms or not tfs:
            raise ValueError("symbols and timeframes must not be empty")
        unknown = [t for t in tfs if t not in TIMEFRAMES]
        if unknown:
            raise ValueError(f"Unknown timeframe(s) {unknown}. Choose from {list(TIMEFRAMES)}")
        if len(syms) * len(tfs) > 200:
            raise ValueError("At most 200 symbol x timeframe combinations per call")
        n = max(1, min(int(count), 100_000))

        written, errors = [], []
        for raw in syms:
            try:
                sym = resolve_symbol(raw)
            except Exception as exc:  # noqa: BLE001
                errors.append([raw, str(exc)[:120]])
                continue
            mt5.symbol_select(sym, True)
            for tf in tfs:
                rates = mt5.copy_rates_from_pos(sym, TIMEFRAMES[tf], 0, n)
                if rates is None or len(rates) == 0:
                    errors.append([f"{sym} {tf}", str(mt5.last_error())[:120]])
                    continue
                rows = candle_rows(rates)
                info = write_csv(export_path(out_dir, "candles", f"{safe_name(sym)}_{tf}.csv"),
                                 CANDLE_COLUMNS, rows)
                written.append([sym, tf, info["rows"], rows[0][0], rows[-1][0], info["path"]])
        return {"exported_files": len(written), "time_basis": TIME_BASIS,
                "last_candle_may_be_open": True,
                "columns": ["symbol", "timeframe", "rows", "first_time", "last_time", "path"],
                "files": written, "errors": errors}
    return run_read(work)


@server.tool(annotations=EXPORT)
def export_deals(date_from: str, date_to: str | None = None, symbol: str | None = None,
                 max_trades: int = 5000, out_dir: str = "") -> str:
    """Write closed trades to CSV instead of the conversation. Same columns as deal_history.
    File: <export folder>/<out_dir>/history/deals.csv. max_trades is capped at 5000."""
    def work():
        payload = closed_trades(date_from, date_to, symbol, max_trades)
        info = write_csv(export_path(out_dir, "history", "deals.csv"),
                         payload["columns"], payload["trades"])
        trades = payload["trades"]
        return {**info, "range": payload["range"], "truncated": payload["truncated"],
                "skipped_still_open_or_incomplete": payload["skipped_still_open_or_incomplete"],
                "first_close": trades[0][8] if trades else None,
                "last_close": trades[-1][8] if trades else None,
                "time_basis": TIME_BASIS}
    return run_read(work)


@server.tool(annotations=EXPORT)
def export_state(out_dir: str = "") -> str:
    """Write a snapshot of the account, open positions and pending orders to CSV.
    Files: <export folder>/<out_dir>/state/account.csv, positions.csv, pending.csv"""
    def work():
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        a = mt5.account_info()
        account = write_csv(
            export_path(out_dir, "state", "account.csv"),
            ["snapshot_utc", "login", "server", "currency", "balance", "equity",
             "floating_profit", "margin", "margin_free", "margin_level_pct", "leverage"],
            [[stamp, a.login, a.server, a.currency, a.balance, a.equity, a.profit,
              a.margin, a.margin_free, a.margin_level, a.leverage]])
        open_positions = write_csv(
            export_path(out_dir, "state", "positions.csv"),
            ["snapshot_utc", *POSITION_COLUMNS],
            [[stamp, *_position_row(p)] for p in (mt5.positions_get() or ())])
        pending = write_csv(
            export_path(out_dir, "state", "pending.csv"),
            ["snapshot_utc", "ticket", "symbol", "type", "lots", "entry_price", "sl", "tp",
             "setup_time", "expiration", "state", "comment"],
            [[stamp, o.ticket, o.symbol, ORDER_TYPE.get(o.type, str(o.type)),
              round(o.volume_current, 2), rnd(o.price_open), rnd(o.sl), rnd(o.tp),
              ts(o.time_setup), ts(o.time_expiration) if o.time_expiration else "",
              ORDER_STATE.get(o.state, str(o.state)), o.comment]
             for o in (mt5.orders_get() or ())])
        return {"snapshot_utc": stamp, "account": account,
                "positions": open_positions, "pending": pending}
    return run_read(work)
