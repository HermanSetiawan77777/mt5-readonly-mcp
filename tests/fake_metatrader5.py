"""In-memory stand-in for the MetaTrader5 package.

The real package only runs on Windows next to a MetaTrader 5 terminal, so the
tests install this module as ``MetaTrader5`` and drive it through ``state``.
"""

from __future__ import annotations

import fnmatch
from collections import namedtuple

TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30 = 1, 5, 15, 30
TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 16385, 16388, 16408
TIMEFRAME_W1, TIMEFRAME_MN1 = 32769, 49153

DEAL_TYPE_BUY, DEAL_TYPE_SELL, DEAL_TYPE_BALANCE = 0, 1, 2
DEAL_ENTRY_IN, DEAL_ENTRY_OUT, DEAL_ENTRY_INOUT, DEAL_ENTRY_OUT_BY = 0, 1, 2, 3
POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1

Account = namedtuple("Account", "login server company trade_mode currency balance equity profit "
                                "margin margin_free margin_level leverage trade_allowed")
Terminal = namedtuple("Terminal", "path")
Deal = namedtuple("Deal", "ticket order position_id symbol type entry volume price time "
                          "profit commission swap fee reason sl tp")
HistoryOrder = namedtuple("HistoryOrder", "ticket sl tp time_setup")
Position = namedtuple("Position", "ticket symbol type volume price_open sl tp price_current "
                                  "profit swap time comment")
PendingOrder = namedtuple("PendingOrder", "ticket symbol type volume_current price_open sl tp "
                                          "time_setup time_expiration state comment")
Symbol = namedtuple("Symbol", "name path description digits point spread trade_mode volume_min "
                              "volume_max volume_step trade_contract_size trade_tick_size "
                              "trade_tick_value currency_profit bid ask swap_long swap_short")
Tick = namedtuple("Tick", "bid ask")


def make_account(trade_allowed=False, **kw):
    base = dict(login=1234567, server="Demo-Server", company="Demo Broker", trade_mode=0,
                currency="USD", balance=1000.0, equity=1010.0, profit=10.0, margin=50.0,
                margin_free=960.0, margin_level=2020.0, leverage=100, trade_allowed=trade_allowed)
    base.update(kw)
    return Account(**base)


def make_symbol(name, bid=100.0, ask=100.1, **kw):
    base = dict(name=name, path=f"Demo\\{name}", description=name, digits=2, point=0.01, spread=10,
                trade_mode=4, volume_min=0.01, volume_max=100.0, volume_step=0.01,
                trade_contract_size=100.0, trade_tick_size=0.01, trade_tick_value=1.0,
                currency_profit="USD", bid=bid, ask=ask, swap_long=0.0, swap_short=0.0)
    base.update(kw)
    return Symbol(**base)


def make_deal(**kw):
    base = dict(ticket=1, order=1, position_id=1, symbol="XAUUSD", type=DEAL_TYPE_BUY,
                entry=DEAL_ENTRY_IN, volume=0.01, price=100.0, time=0, profit=0.0,
                commission=0.0, swap=0.0, fee=0.0, reason=0, sl=0.0, tp=0.0)
    base.update(kw)
    return Deal(**base)


class State:
    def reset(self):
        self.account = make_account()
        self.initialize_ok = True
        self.initialized = False
        self.terminal_path = ""
        self.calls = []
        self.deals, self.history_orders = [], []
        self.positions, self.pending = [], []
        self.symbols = {}
        self.rates = {}


state = State()
state.reset()


def initialize(path=None):
    state.calls.append(("initialize", path))
    state.initialized = state.initialize_ok
    state.terminal_path = path or ""
    return state.initialize_ok


def shutdown():
    state.calls.append("shutdown")
    state.initialized = False


def terminal_info():
    return Terminal(state.terminal_path) if state.initialized else None


def last_error():
    return (-1, "fake error")


def account_info():
    return state.account


def order_send(*_args, **_kwargs):  # the guard must replace this
    state.calls.append("order_send")
    return "sent"


def order_check(*_args, **_kwargs):  # the guard must replace this
    state.calls.append("order_check")
    return "checked"


def history_deals_get(date_from=None, date_to=None, position=None):
    if position is not None:
        return tuple(d for d in state.deals if d.position_id == position)
    lo, hi = date_from.timestamp(), date_to.timestamp()
    return tuple(d for d in state.deals if lo <= d.time < hi)


def history_orders_get(date_from=None, date_to=None, ticket=None):
    if ticket is not None:
        return tuple(o for o in state.history_orders if o.ticket == ticket)
    lo, hi = date_from.timestamp(), date_to.timestamp()
    return tuple(o for o in state.history_orders if lo <= o.time_setup < hi)


def positions_get():
    return tuple(state.positions)


def orders_get():
    return tuple(state.pending)


def symbol_info(name):
    return state.symbols.get(name)


def symbols_get(pattern="*"):
    return tuple(s for n, s in state.symbols.items() if fnmatch.fnmatchcase(n, pattern))


def symbol_select(_name, _enable=True):
    return True


def symbol_info_tick(name):
    s = state.symbols.get(name)
    return Tick(s.bid, s.ask) if s else None


def copy_rates_from_pos(symbol, _timeframe, _start, count):
    rates = state.rates.get(symbol)
    return None if rates is None else rates[-count:]
