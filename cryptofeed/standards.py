'''
Copyright (C) 2017-2019  Bryant Moscon - bmoscon@gmail.com

Please see the LICENSE file for the terms and conditions
associated with this software.


Contains all code to normalize and standardize the differences
between exchanges. These include trading pairs, timestamps, and
data channel names
'''
import logging
import pandas as pd

from cryptofeed.defines import (L2_BOOK, L3_BOOK, TRADES, TICKER, VOLUME, FUNDING, UNSUPPORTED, BITFINEX, GEMINI,
                                POLONIEX, HITBTC, BITSTAMP, COINBASE, BITMEX, KRAKEN, KRAKEN_FUTURES, BINANCE, EXX, HUOBI, HUOBI_US, HUOBI_DM, OKCOIN,
                                OKEX, COINBENE, BYBIT, FTX, TRADES_SWAP, TICKER_SWAP, L2_BOOK_SWAP, LIMIT, MARKET, FILL_OR_KILL, IMMEDIATE_OR_CANCEL, MAKER_OR_CANCEL, DERIBIT, INSTRUMENT)
from cryptofeed.pairs import gen_pairs
from cryptofeed.exceptions import UnsupportedTradingPair, UnsupportedDataFeed, UnsupportedTradingOption


LOG = logging.getLogger('feedhandler')


_std_trading_pairs = {}
_exchange_to_std = {}


def load_exchange_pair_mapping(exchange):
    if exchange in {BITMEX, DERIBIT, KRAKEN_FUTURES}:
        return
    mapping = gen_pairs(exchange)
    for std, exch in mapping.items():
        _exchange_to_std[exch] = std
        if std in _std_trading_pairs:
            _std_trading_pairs[std][exchange] = exch
        else:
            _std_trading_pairs[std] = {exchange: exch}


def pair_std_to_exchange(pair, exchange):
    # bitmex does its own validation of trading pairs dynamically
    if exchange in {BITMEX, DERIBIT, KRAKEN_FUTURES}:
        return pair
    if pair in _std_trading_pairs:
        try:
            return _std_trading_pairs[pair][exchange]
        except KeyError:
            raise UnsupportedTradingPair(f'{pair} is not supported on {exchange}')
    else:
        # Bitfinex supports funding pairs that are single currencies, prefixed with f
        if exchange == BITFINEX and '-' not in pair:
            return f"f{pair}"
        raise UnsupportedTradingPair(f'{pair} is not supported on {exchange}')


def pair_exchange_to_std(pair):
    if pair in _exchange_to_std:
        return _exchange_to_std[pair]
    # Bitfinex funding currency
    if pair[0] == 'f':
        return pair[1:]
    return None


def timestamp_normalize(exchange, ts):
    if exchange in {BITMEX, COINBASE, HITBTC, OKCOIN, OKEX, BYBIT, FTX}:
        return pd.Timestamp(ts).timestamp()
    elif exchange in  {HUOBI, HUOBI_US, HUOBI_DM, BITFINEX, COINBENE, DERIBIT, BINANCE, GEMINI}:
        return ts / 1000.0
    elif exchange in {BITSTAMP}:
        return ts / 1000000.0
    return ts


_feed_to_exchange_map = {
    L2_BOOK: {
        BITFINEX: 'book-P0-F0-100',
        POLONIEX: L2_BOOK,
        HITBTC: 'subscribeOrderbook',
        COINBASE: 'level2',
        BITMEX: 'orderBookL2',
        BITSTAMP: 'order_book',
        KRAKEN: 'book',
        KRAKEN_FUTURES: 'book',
        BINANCE: 'depth',
        EXX: 'ENTRUST_ADD',
        HUOBI: 'depth.step0',
        HUOBI_US: 'depth.step0',
        HUOBI_DM: 'depth.step0',
        OKCOIN: 'spot/depth',
        OKEX: 'spot/depth',
        COINBENE: L2_BOOK,
        DERIBIT: 'book',
        BYBIT: 'order_book_25L1',
        FTX: 'orderbook',
        GEMINI: L2_BOOK
    },
    L3_BOOK: {
        BITFINEX: 'book-R0-F0-100',
        BITSTAMP: 'detail_order_book',
        HITBTC: UNSUPPORTED,
        COINBASE: 'full',
        BITMEX: UNSUPPORTED,
        POLONIEX: UNSUPPORTED,  # supported by specifying a trading pair as the channel,
        KRAKEN: UNSUPPORTED,
        KRAKEN_FUTURES: UNSUPPORTED,
        BINANCE: UNSUPPORTED,
        EXX: UNSUPPORTED,
        HUOBI: UNSUPPORTED,
        HUOBI_US: UNSUPPORTED,
        HUOBI_DM: UNSUPPORTED,
        OKCOIN: UNSUPPORTED,
        OKEX: UNSUPPORTED,
        BYBIT: UNSUPPORTED,
        FTX: UNSUPPORTED,
        GEMINI: UNSUPPORTED
    },
    TRADES: {
        POLONIEX: TRADES,
        HITBTC: 'subscribeTrades',
        BITSTAMP: 'live_trades',
        BITFINEX: 'trades',
        COINBASE: 'matches',
        BITMEX: 'trade',
        KRAKEN: 'trade',
        KRAKEN_FUTURES: 'trade',
        BINANCE: 'aggTrade',
        EXX: 'TRADE',
        HUOBI: 'trade.detail',
        HUOBI_US: 'trade.detail',
        HUOBI_DM: 'trade.detail',
        OKCOIN: 'spot/trade',
        OKEX: 'spot/trade',
        COINBENE: TRADES,
        DERIBIT: 'trades',
        BYBIT:  'trade',
        FTX: 'trades',
        GEMINI: TRADES
    },
    TICKER: {
        POLONIEX: 1002,
        HITBTC: 'subscribeTicker',
        BITFINEX: 'ticker',
        BITSTAMP: UNSUPPORTED,
        COINBASE: 'ticker',
        BITMEX: UNSUPPORTED,
        KRAKEN: TICKER,
        KRAKEN_FUTURES: 'ticker_lite',
        BINANCE: 'ticker',
        HUOBI: UNSUPPORTED,
        HUOBI_US: UNSUPPORTED,
        HUOBI_DM: UNSUPPORTED,
        OKCOIN: 'spot/ticker',
        OKEX: 'spot/ticker',
        COINBENE: TICKER,
        DERIBIT: "ticker",
        BYBIT: UNSUPPORTED,
        FTX: "ticker",
        GEMINI: UNSUPPORTED
    },
    VOLUME: {
        POLONIEX: 1003
    },
    FUNDING: {
        BITMEX: 'funding',
        BITFINEX: 'trades'
    },
    TRADES_SWAP: {
        OKEX: 'swap/trade'
    },
    TICKER_SWAP: {
        OKEX: 'swap/ticker'
    },
    L2_BOOK_SWAP: {
        OKEX: 'swap/depth'
    },
    INSTRUMENT: {
        BITMEX: 'instrument'
    }
}


_exchange_options = {
    LIMIT: {
        KRAKEN: 'limit',
        GEMINI: 'exchange limit',
        POLONIEX: 'limit',
        COINBASE: 'limit'
    },
    MARKET: {
        KRAKEN: 'market',
        GEMINI: UNSUPPORTED,
        POLONIEX: UNSUPPORTED,
        COINBASE: 'market'
    },
    FILL_OR_KILL: {
        GEMINI: 'fill-or-kill',
        POLONIEX: 'fillOrKill',
        COINBASE: {'time_in_force': 'FOK'},
        KRAKEN: UNSUPPORTED
    },
    IMMEDIATE_OR_CANCEL: {
        GEMINI: 'immediate-or-cancel',
        POLONIEX: 'immediateOrCancel',
        COINBASE: {'time_in_force': 'IOC'},
        KRAKEN: UNSUPPORTED
    },
    MAKER_OR_CANCEL: {
        GEMINI: 'maker-or-cancel',
        POLONIEX: 'postOnly',
        COINBASE: {'post_only': 1},
        KRAKEN: 'post'
    }
}


def normalize_trading_options(exchange, option):
    if option not in _exchange_options:
        raise UnsupportedTradingOption
    if exchange not in _exchange_options[option]:
        raise UnsupportedTradingOption

    ret = _exchange_options[option][exchange]
    if ret == UNSUPPORTED:
        raise UnsupportedTradingOption
    return ret


def feed_to_exchange(exchange, feed):
    if exchange == POLONIEX:
        if feed not in _feed_to_exchange_map:
            return pair_std_to_exchange(feed, POLONIEX)

    ret = _feed_to_exchange_map[feed][exchange]
    if ret == UNSUPPORTED:
        LOG.error(f"{feed} is not supported on {exchange}")
        raise UnsupportedDataFeed(f"{feed} is not supported on {exchange}")
    return ret
