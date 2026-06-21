from yammyquant.exchanges.fees import fee_schedule, FeeSchedule, FEE_SCHEDULE


def test_known_exchange_schedules():
    assert fee_schedule("binance").taker == 0.001
    assert fee_schedule("upbit").maker == 0.0005
    assert fee_schedule("BITHUMB").taker == 0.0004        # case-insensitive
    assert fee_schedule("kis").taker == 0.00015


def test_unknown_exchange_falls_back():
    s = fee_schedule("nonesuch")
    assert s.maker == 0.001 and s.taker == 0.001


def test_rate_by_order_type():
    s = FeeSchedule(maker=0.0002, taker=0.0007)
    assert s.rate("limit") == 0.0002      # resting limit -> maker
    assert s.rate("market") == 0.0007     # crosses the book -> taker
    assert s.rate("stop") == 0.0007       # stop executes as market -> taker


def test_exchange_fees_method():
    # the base Exchange.fees() returns the static schedule for the venue
    from yammyquant.exchanges import get_exchange
    fees = get_exchange("binance").fees()
    assert fees == {"maker": 0.001, "taker": 0.001}


def test_all_schedules_sane():
    for name, s in FEE_SCHEDULE.items():
        assert 0 <= s.maker < 0.01 and 0 <= s.taker < 0.01, name
