"""Read helpers on top of the MetaTrader5 package.

All times are the broker's server time, which is what MetaTrader 5 returns.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
}

ACCOUNT_TYPE = {0: "DEMO", 1: "CONTEST", 2: "REAL"}

DEAL_SIDE = {mt5.DEAL_TYPE_BUY: "BUY", mt5.DEAL_TYPE_SELL: "SELL"}
ENTRY_IN = mt5.DEAL_ENTRY_IN
ENTRY_EXIT = {mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY, mt5.DEAL_ENTRY_INOUT}

# Why a deal was executed (standard MetaTrader 5 values).
DEAL_REASON = {
    0: "MANUAL_DESKTOP", 1: "MANUAL_MOBILE", 2: "MANUAL_WEB", 3: "EA_OR_SCRIPT",
    4: "STOP_LOSS", 5: "TAKE_PROFIT", 6: "STOP_OUT", 7: "ROLLOVER",
    8: "VARIATION_MARGIN", 9: "SPLIT",
}

ORDER_TYPE = {
    0: "BUY", 1: "SELL", 2: "BUY_LIMIT", 3: "SELL_LIMIT",
    4: "BUY_STOP", 5: "SELL_STOP", 6: "BUY_STOP_LIMIT", 7: "SELL_STOP_LIMIT",
}
ORDER_STATE = {
    0: "STARTED", 1: "PLACED", 2: "CANCELED", 3: "PARTIAL", 4: "FILLED",
    5: "REJECTED", 6: "EXPIRED", 7: "REQUEST_ADD", 8: "REQUEST_MODIFY", 9: "REQUEST_CANCEL",
}

CANDLE_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread_points"]
TRADE_COLUMNS = ["position_id", "symbol", "side", "lots", "open_time", "open_price",
                 "sl_initial", "tp_initial", "close_time", "close_price",
                 "exit_reason", "profit", "commission", "swap", "fee", "net"]
TIME_BASIS = "broker server time"


def ts(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_date(text: str) -> datetime:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Dates must be YYYY-MM-DD, got {text!r}") from exc


def rnd(x, n: int = 5) -> float:
    return round(float(x), n)


def split_list(text) -> list[str]:
    """Split 'A, B;C' into ['A', 'B', 'C']."""
    return [t.strip() for t in str(text or "").replace(";", ",").split(",") if t.strip()]


def resolve_symbol(symbol: str) -> str:
    """Accept 'XAUUSD' when the broker lists it with a suffix, e.g. 'XAUUSDm'."""
    sym = symbol.strip()
    if mt5.symbol_info(sym) is not None:
        return sym
    candidates = [s.name for s in (mt5.symbols_get(f"*{sym}*") or ())]
    prefixed = [c for c in candidates if c.upper().startswith(sym.upper())]
    if len(prefixed) == 1:
        return prefixed[0]
    if candidates:
        raise ValueError(f"Symbol {sym!r} is ambiguous or missing. Candidates: {candidates[:15]}")
    raise ValueError(f"Symbol {sym!r} was not found at this broker.")


def candle_rows(rates) -> list[list]:
    return [[ts(r["time"]), rnd(r["open"]), rnd(r["high"]), rnd(r["low"]),
             rnd(r["close"]), int(r["tick_volume"]), int(r["spread"])] for r in rates]


def _weighted_price(deals) -> float:
    volume = sum(d.volume for d in deals)
    return sum(d.price * d.volume for d in deals) / volume if volume else 0.0


def closed_trades(date_from: str, date_to: str | None, symbol: str | None, max_trades: int) -> dict:
    """Closed positions in a date range, one row per position (entry and exit merged).

    MetaTrader 5 stores deals, not trades: a position has one or more entry deals
    and one or more exit deals. This groups deals by position id, uses volume-
    weighted prices, takes the initial SL/TP from the entry deal or its order,
    and reports why the position was closed.
    """
    d_from = parse_date(date_from)
    d_to = (parse_date(date_to) if date_to else datetime.now(timezone.utc)) + timedelta(days=1)
    limit = max(1, min(int(max_trades), 5000))
    deals = mt5.history_deals_get(d_from, d_to) or ()
    orders = {o.ticket: o for o in (mt5.history_orders_get(d_from, d_to) or ())}

    by_position: dict[int, list] = {}
    for d in deals:
        if d.type not in DEAL_SIDE:
            continue  # balance, credit, commission and other non-trade deals
        if symbol and symbol.upper() not in d.symbol.upper():
            continue
        by_position.setdefault(d.position_id, []).append(d)

    trades, skipped = [], 0
    for position_id, ds in by_position.items():
        exits = [d for d in ds if d.entry in ENTRY_EXIT]
        if not exits:
            skipped += 1  # still open
            continue
        entries = [d for d in ds if d.entry == ENTRY_IN]
        if not entries:  # opened before date_from: fetch the whole position
            full = mt5.history_deals_get(position=position_id) or ()
            entries = [d for d in full if d.entry == ENTRY_IN]
        if not entries:
            skipped += 1
            continue

        first_in, last_out = entries[0], max(exits, key=lambda d: d.time)
        first_in_fields = first_in._asdict()
        sl0, tp0 = first_in_fields.get("sl", 0) or 0, first_in_fields.get("tp", 0) or 0
        if not sl0 and not tp0:
            order = orders.get(first_in.order)
            if order is None:
                found = mt5.history_orders_get(ticket=first_in.order) or ()
                order = found[0] if found else None
            if order is not None:
                sl0, tp0 = order.sl, order.tp

        all_deals = entries + exits
        profit = sum(d.profit for d in exits)
        commission = sum(d.commission for d in all_deals)
        swap = sum(d.swap for d in all_deals)
        fee = sum(d._asdict().get("fee", 0) or 0 for d in all_deals)

        trades.append([
            position_id, first_in.symbol, DEAL_SIDE[first_in.type],
            round(sum(d.volume for d in entries), 2),
            ts(first_in.time), rnd(_weighted_price(entries)),
            rnd(sl0), rnd(tp0),
            ts(last_out.time), rnd(_weighted_price(exits)),
            DEAL_REASON.get(last_out.reason, str(last_out.reason)),
            round(profit, 2), round(commission, 2), round(swap, 2), round(fee, 2),
            round(profit + commission + swap + fee, 2),
        ])

    trades.sort(key=lambda t: t[8])  # by close time
    truncated = len(trades) > limit
    if truncated:
        trades = trades[-limit:]
    return {
        "time_basis": TIME_BASIS,
        "range": {"from": date_from, "to": date_to or "now"},
        "count": len(trades),
        "truncated": truncated,
        "skipped_still_open_or_incomplete": skipped,
        "note": "sl_initial/tp_initial = 0 means no SL/TP at entry. Later SL/TP changes "
                "are not stored in the MetaTrader 5 deal history.",
        "columns": TRADE_COLUMNS,
        "trades": trades,
    }
