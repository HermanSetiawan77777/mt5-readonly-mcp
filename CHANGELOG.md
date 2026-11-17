# Changelog

## 1.0.0 (2026-11)

First public release.

- 11 tools: account info, positions, pending orders, closed-trade history, candles, symbol info, symbol list, quotes, and CSV export of candles, history and account state.
- Read-only enforced in three layers: trading functions disabled, fail-closed `trade_allowed` check on every call, dedicated terminal only.
- Export tools confined to `MT5_EXPORT_DIR`.
- MCP tool annotations on every tool.
- Tests with an in-memory MetaTrader5 fake; CI on Linux and a Windows smoke test with the real package.
