"""Command line entry point.

    mt5-readonly-mcp            run the MCP server over stdio (what Claude Desktop does)
    mt5-readonly-mcp --check    verify the connection and the read-only guard, then exit
"""

from __future__ import annotations

import argparse
import sys

import MetaTrader5 as mt5

from . import __version__
from .data import ACCOUNT_TYPE
from .export import export_root
from .guard import connect_and_guard, lock


def check() -> int:
    """Connect once, print what the server would see, and return an exit code."""
    try:
        with lock:
            account = connect_and_guard()
            terminal = mt5.terminal_info()
        print("OK: connected, read-only mode verified")
        print(f"Account: {account.login} @ {account.server} "
              f"({ACCOUNT_TYPE.get(account.trade_mode, account.trade_mode)})")
        print(f"Terminal: {terminal.path}")
        print(f"Exports: {export_root()}")
        print(f"trade_allowed = {account.trade_allowed} (must be False)")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")
        return 1
    finally:
        mt5.shutdown()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mt5-readonly-mcp",
                                     description="Read-only MCP server for MetaTrader 5.")
    parser.add_argument("--check", action="store_true",
                        help="verify the connection and the read-only guard, then exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.check:
        sys.exit(check())

    from .server import server  # imported here so --check and --version stay fast
    server.run()  # stdio transport


if __name__ == "__main__":
    main()
