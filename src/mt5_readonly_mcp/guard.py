"""Safety layers that keep the server read-only.

Layer 1  The trading functions of the MetaTrader5 package are replaced with a
         function that always raises, so they cannot run even by mistake.
Layer 2  Fail-closed account check: if the logged-in account is allowed to
         trade (master password instead of investor password), every tool call
         is refused. The check runs on every call, not only at start-up.
Layer 3  The server connects only to the terminal named in MT5_TERMINAL_PATH,
         a terminal dedicated to this server. Without it, nothing runs.

The server never stores or receives a password: the dedicated terminal keeps
the investor password that was saved when you logged in by hand.
"""

from __future__ import annotations

import os
import threading

import MetaTrader5 as mt5

BLOCKED_FUNCTIONS = ("order_send", "order_check")


class ReadOnlyViolation(RuntimeError):
    """Raised when something would break the read-only guarantee."""


class ConfigurationError(RuntimeError):
    """Raised when the server is not configured correctly."""


def _blocked(*_args, **_kwargs):
    raise ReadOnlyViolation("Blocked: this server is read-only and trading functions are disabled.")


def disable_trading_functions(module=mt5) -> list[str]:
    """Layer 1: replace trading functions on the MetaTrader5 module."""
    disabled = []
    for name in BLOCKED_FUNCTIONS:
        if hasattr(module, name):
            setattr(module, name, _blocked)
            disabled.append(name)
    return disabled


disable_trading_functions()

# The MetaTrader5 package is not thread-safe: every call goes through this lock.
lock = threading.Lock()
_state = {"connected": False}


def terminal_path() -> str:
    return os.environ.get("MT5_TERMINAL_PATH", "").strip()


def connect_and_guard():
    """Layers 2 and 3: connect to the dedicated terminal and verify it is read-only.

    Returns the account info. Must be called while holding ``lock``.
    """
    path = terminal_path()
    if not path:
        raise ConfigurationError(
            "MT5_TERMINAL_PATH is not set. Point it to terminal64.exe of a MetaTrader 5 "
            r"terminal dedicated to this server, e.g. C:\MT5-ReadOnly\terminal64.exe"
        )
    if not os.path.isfile(path):
        raise ConfigurationError(f"terminal64.exe not found at: {path}")

    if not _state["connected"] or mt5.terminal_info() is None:
        if not mt5.initialize(path=path):
            error = mt5.last_error()
            mt5.shutdown()
            raise ConnectionError(
                f"Could not connect to MetaTrader 5 {error}. Make sure the dedicated terminal "
                "is logged in with the investor password and 'Save password' is ticked."
            )
        _state["connected"] = True

    account = mt5.account_info()
    if account is None:
        raise ConnectionError(f"The terminal is running but no account is logged in {mt5.last_error()}")

    if account.trade_allowed:
        mt5.shutdown()
        _state["connected"] = False
        raise ReadOnlyViolation(
            "Refused (fail-closed): the account in this terminal is allowed to trade. "
            "Log the dedicated terminal in with the INVESTOR (read-only) password."
        )
    return account
