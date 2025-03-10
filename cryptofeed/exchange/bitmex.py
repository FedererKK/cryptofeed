'''
Copyright (C) 2017-2019  Bryant Moscon - bmoscon@gmail.com

Please see the LICENSE file for the terms and conditions
associated with this software.
'''
import json
import logging
from collections import defaultdict
from decimal import Decimal

import requests
from sortedcontainers import SortedDict as sd

from cryptofeed.feed import Feed
from cryptofeed.defines import L2_BOOK, BUY, SELL, BID, ASK, TRADES, FUNDING, BITMEX, INSTRUMENT
from cryptofeed.standards import timestamp_normalize


LOG = logging.getLogger('feedhandler')


class Bitmex(Feed):
    id = BITMEX
    api = 'https://www.bitmex.com/api/v1/'

    def __init__(self, pairs=None, channels=None, callbacks=None, **kwargs):
        super().__init__('wss://www.bitmex.com/realtime', pairs=pairs, channels=channels, callbacks=callbacks, **kwargs)

        active_pairs = self.get_active_symbols()
        if self.config:
            pairs = list(self.config.values())
            self.pairs = [pair for inner in pairs for pair in inner]

        for pair in self.pairs:
            if not pair.startswith('.'):
                if pair not in active_pairs:
                    raise ValueError("{} is not active on BitMEX".format(pair))
        self._reset()

    def _reset(self):
        self.partial_received = False
        self.order_id = {}
        for pair in self.pairs:
            self.l2_book[pair] = {BID: sd(), ASK: sd()}
            self.order_id[pair] = defaultdict(dict)

    @staticmethod
    def get_symbol_info():
        return requests.get(Bitmex.api + 'instrument/').json()

    @staticmethod
    def get_active_symbols_info():
        return requests.get(Bitmex.api + 'instrument/active').json()

    @staticmethod
    def get_active_symbols():
        symbols = []
        for data in Bitmex.get_active_symbols_info():
            symbols.append(data['symbol'])
        return symbols

    async def _trade(self, msg):
        """
        trade msg example

        {
            'timestamp': '2018-05-19T12:25:26.632Z',
            'symbol': 'XBTUSD',
            'side': 'Buy',
            'size': 40,
            'price': 8335,
            'tickDirection': 'PlusTick',
            'trdMatchID': '5f4ecd49-f87f-41c0-06e3-4a9405b9cdde',
            'grossValue': 479920,
            'homeNotional': Decimal('0.0047992'),
            'foreignNotional': 40
        }
        """
        for data in msg['data']:
            ts = timestamp_normalize(self.id, data['timestamp'])
            await self.callback(TRADES, feed=self.id,
                                         pair=data['symbol'],
                                         side=BUY if data['side'] == 'Buy' else SELL,
                                         amount=Decimal(data['size']),
                                         price=Decimal(data['price']),
                                         order_id=data['trdMatchID'],
                                         timestamp=ts)

    async def _book(self, msg: dict, timestamp: float):
        """
        the Full bitmex book
        """
        pair = None
        delta = {BID: [], ASK: []}
        # if we reset the book, force a full update
        forced = False
        if not self.partial_received:
            # per bitmex documentation messages received before partial
            # should be discarded
            if msg['action'] != 'partial':
                return
            self.partial_received = True
            forced = True

        if msg['action'] == 'partial' or msg['action'] == 'insert':
            for data in msg['data']:
                side = BID if data['side'] == 'Buy' else ASK
                price = Decimal(data['price'])
                pair = data['symbol']
                size = Decimal(data['size'])
                order_id = data['id']

                self.l2_book[pair][side][price] = size
                self.order_id[pair][side][order_id] = price
                delta[side].append((price, size))
        elif msg['action'] == 'update':
            for data in msg['data']:
                side = BID if data['side'] == 'Buy' else ASK
                pair = data['symbol']
                update_size = Decimal(data['size'])
                order_id = data['id']

                price = self.order_id[pair][side][order_id]

                self.l2_book[pair][side][price] = update_size
                self.order_id[pair][side][order_id] = price
                delta[side].append((price, update_size))
        elif msg['action'] == 'delete':
            for data in msg['data']:
                pair = data['symbol']
                side = BID if data['side'] == 'Buy' else ASK
                order_id = data['id']

                delete_price = self.order_id[pair][side][order_id]
                del self.order_id[pair][side][order_id]
                del self.l2_book[pair][side][delete_price]

                delta[side].append((delete_price, 0))

        else:
            LOG.warning("%s: Unexpected l2 Book message %s", self.id, msg)
            return

        await self.book_callback(pair, L2_BOOK, forced, delta, timestamp)

    async def _funding(self, msg):
        """
        {'table': 'funding',
         'action': 'partial',
         'keys': ['timestamp', 'symbol'],
         'types': {
             'timestamp': 'timestamp',
             'symbol': 'symbol',
             'fundingInterval': 'timespan',
             'fundingRate': 'float',
             'fundingRateDaily': 'float'
            },
         'foreignKeys': {
             'symbol': 'instrument'
            },
         'attributes': {
             'timestamp': 'sorted',
             'symbol': 'grouped'
            },
         'filter': {'symbol': 'XBTUSD'},
         'data': [{
             'timestamp': '2018-08-21T20:00:00.000Z',
             'symbol': 'XBTUSD',
             'fundingInterval': '2000-01-01T08:00:00.000Z',
             'fundingRate': Decimal('-0.000561'),
             'fundingRateDaily': Decimal('-0.001683')
            }]
        }
        """
        for data in msg['data']:
            ts = timestamp_normalize(self.id, data['timestamp'])
            await self.callback(FUNDING, feed=self.id,
                                          pair=data['symbol'],
                                          timestamp=ts,
                                          interval=data['fundingInterval'],
                                          rate=data['fundingRate'],
                                          rate_daily=data['fundingRateDaily']
                                          )

    async def _instrument(self, msg):
        for data in msg['data']:
            ts = timestamp_normalize(self.id, data['timestamp'])
            data['timestamp'] = ts
            await self.callback(INSTRUMENT, feed=self.id,
                                            pair=data['symbol'],
                                            **data
                                            )

    async def message_handler(self, msg: str, timestamp: float):
        msg = json.loads(msg, parse_float=Decimal)
        if 'info' in msg:
            LOG.info("%s - info message: %s", self.id, msg)
        elif 'subscribe' in msg:
            if not msg['success']:
                LOG.error("%s: subscribe failed: %s", self.id, msg)
        elif 'error' in msg:
            LOG.error("%s: Error message from exchange: %s", self.id, msg)
        else:
            if msg['table'] == 'trade':
                await self._trade(msg)
            elif msg['table'] == 'orderBookL2':
                await self._book(msg, timestamp)
            elif msg['table'] == 'funding':
                await self._funding(msg)
            elif msg['table'] == 'instrument':
                await self._instrument(msg)
            else:
                LOG.warning("%s: Unhandled message %s", self.id, msg)

    async def subscribe(self, websocket):
        self._reset()
        chans = []
        for channel in self.channels if not self.config else self.config:
            for pair in self.pairs if not self.config else self.config[channel]:
                chans.append("{}:{}".format(channel, pair))

        await websocket.send(json.dumps({"op": "subscribe",
                                         "args": chans}))
