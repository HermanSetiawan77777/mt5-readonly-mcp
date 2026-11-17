from datetime import datetime, timezone

from mt5_readonly_mcp.data import closed_trades


def t(day, hour=0):
    return int(datetime(2026, 1, day, hour, tzinfo=timezone.utc).timestamp())


def row(result, index=0):
    return dict(zip(result["columns"], result["trades"][index], strict=True))


def test_scaled_in_position_is_merged_into_one_trade(mt5):
    mt5.state.deals = [
        mt5.make_deal(ticket=1, position_id=10, volume=0.01, price=100.0, time=t(5, 1),
                      commission=-0.1, sl=95.0, tp=110.0),
        mt5.make_deal(ticket=2, position_id=10, volume=0.03, price=104.0, time=t(5, 2),
                      commission=-0.3),
        mt5.make_deal(ticket=3, position_id=10, type=mt5.DEAL_TYPE_SELL, entry=mt5.DEAL_ENTRY_OUT,
                      volume=0.04, price=110.0, time=t(5, 3), profit=28.0, commission=-0.4,
                      swap=-1.0, reason=5),
    ]
    result = closed_trades("2026-01-01", "2026-01-31", None, 100)
    trade = row(result)
    assert result["count"] == 1
    assert trade["side"] == "BUY"
    assert trade["lots"] == 0.04
    assert trade["open_price"] == 103.0  # (0.01*100 + 0.03*104) / 0.04
    assert (trade["sl_initial"], trade["tp_initial"]) == (95.0, 110.0)
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["net"] == round(28.0 - 0.8 - 1.0, 2)


def test_balance_deals_and_open_positions_are_not_trades(mt5):
    mt5.state.deals = [
        mt5.make_deal(ticket=1, position_id=0, type=mt5.DEAL_TYPE_BALANCE, time=t(2), profit=500.0),
        mt5.make_deal(ticket=2, position_id=20, time=t(3)),  # entry only: still open
    ]
    result = closed_trades("2026-01-01", "2026-01-31", None, 100)
    assert result["count"] == 0
    assert result["skipped_still_open_or_incomplete"] == 1


def test_position_opened_before_the_range_still_gets_its_entry(mt5):
    mt5.state.deals = [
        mt5.make_deal(ticket=1, position_id=30, price=200.0, time=t(1)),
        mt5.make_deal(ticket=2, position_id=30, entry=mt5.DEAL_ENTRY_OUT, type=mt5.DEAL_TYPE_SELL,
                      price=190.0, time=t(20), profit=-10.0, reason=4),
    ]
    trade = row(closed_trades("2026-01-15", "2026-01-31", None, 100))
    assert trade["open_price"] == 200.0
    assert trade["exit_reason"] == "STOP_LOSS"


def test_initial_sl_tp_fall_back_to_the_opening_order(mt5):
    mt5.state.deals = [
        mt5.make_deal(ticket=1, order=77, position_id=40, type=mt5.DEAL_TYPE_SELL, time=t(4)),
        mt5.make_deal(ticket=2, position_id=40, entry=mt5.DEAL_ENTRY_OUT, time=t(4, 5)),
    ]
    mt5.state.history_orders = [mt5.HistoryOrder(ticket=77, sl=105.0, tp=90.0, time_setup=t(4))]
    trade = row(closed_trades("2026-01-01", None, None, 100))
    assert trade["side"] == "SELL"
    assert (trade["sl_initial"], trade["tp_initial"]) == (105.0, 90.0)


def test_symbol_filter_matches_partially_and_newest_trades_are_kept(mt5):
    deals = []
    for i, symbol in enumerate(["XAUUSDm", "BTCUSD", "XAUUSDm", "XAUUSDm"], start=1):
        deals += [mt5.make_deal(ticket=i * 10, position_id=i, symbol=symbol, time=t(i)),
                  mt5.make_deal(ticket=i * 10 + 1, position_id=i, symbol=symbol,
                                entry=mt5.DEAL_ENTRY_OUT, time=t(i, 1))]
    mt5.state.deals = deals
    result = closed_trades("2026-01-01", "2026-01-31", "xauusd", 2)
    assert result["truncated"] is True
    assert [r[0] for r in result["trades"]] == [3, 4]
