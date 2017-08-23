# Copyright (C) 2013, Maxime Biais <maxime@biais.org>

import public_markets
import observers
import config
import time
import logging
import json
from concurrent.futures import ThreadPoolExecutor, wait
# logger = logging.getLogger(__name__)
comment = lambda msg: logging.getLogger(__name__).log(logging.COMMENT, msg)
# comment = logging.genComment(logging.getLogger(__name__))
# comment = logging.genComment(logger, 10)

class Arbitrer(object):
    def __init__(self):
        self.markets = []
        self.observers = []
        self.depths = {}
        comment('init markets')
        self.init_markets(config.markets)
        comment('init observers')
        self.init_observers(config.observers)
        comment('init threadpool')
        self.threadpool = ThreadPoolExecutor(max_workers=10)

    def init_markets(self, markets):
        self.market_names = markets
        for market_name in markets:
            try:
                comment('init market: {}'.format(market_name))
                exec('import public_markets.' + market_name.lower())
                market = eval('public_markets.' + market_name.lower() + '.' +
                              market_name + '()')
                self.markets.append(market)
            except (ImportError, AttributeError) as e:
                print("%s market name is invalid: Ignored (you should check your config file)" % (market_name))

    def init_observers(self, _observers):
        self.observer_names = _observers
        for observer_name in _observers:
            try:
                exec('import observers.' + observer_name.lower())
                observer = eval('observers.' + observer_name.lower() + '.' +
                                observer_name + '()')
                self.observers.append(observer)
            except (ImportError, AttributeError) as e:
                print("%s observer name is invalid: Ignored (you should check your config file)" % (observer_name))

    def price_is_profitable(self, ask_price, bid_price):
        return ask_price < bid_price

    def arbitrage_depth_opportunity(self, kask, kbid):

        # initial counters
        aski = bidi = 0
        total_ask_volume = total_bid_volume = 0
        total_ask_fee = total_bid_fee = 0

        while True:
            cur_ask_price = self.depths[kask]['asks'][aski]['price']
            cur_bid_price = self.depths[kbid]['bids'][bidi]['price']
            cur_ask_volume = self.depths[kask]['asks'][aski]['amount']
            cur_bid_volume = self.depths[kbid]['bids'][bidi]['amount']
            if self.price_is_profitable(cur_ask_price, cur_bid_price):
                if total_ask_volume + cur_ask_volume <= total_bid_volume + cur_bid_volume:
                    # increase aski, and buy cur_ask_volume
                    aski += 1
                    total_ask_volume += cur_ask_volume
                    total_ask_fee += cur_ask_volume * cur_ask_price

                if total_ask_volume + cur_ask_volume >= total_bid_volume + cur_bid_volume:
                    # increase bidi, and buy cur_bid_volume
                    bidi += 1
                    total_bid_volume += cur_bid_volume
                    total_bid_fee += cur_bid_volume * cur_bid_price
            else:
                if total_ask_volume > total_bid_volume:
                    # add some bid volume
                    cur_bid_volume = total_ask_volume - total_bid_volume
                    total_bid_volume += cur_bid_volume
                    total_bid_fee += cur_bid_volume * cur_bid_price
                    aski -= 1
                elif total_ask_volume < total_bid_volume:
                    # add some ask volume
                    cur_ask_volume = total_bid_volume - total_ask_volume
                    total_ask_volume += cur_ask_volume
                    total_ask_fee += cur_ask_volume * cur_ask_price
                    bidi -= 1
                else:
                    aski -= 1
                    bidi -= 1
                break

        best_profit = total_bid_fee - total_ask_fee
        best_volume = total_ask_volume
        best_w_buyprice = total_ask_fee / total_ask_volume
        best_w_sellprice = total_bid_fee / total_bid_volume

        comment('aski, bidi, profit, askprice, bidprice')
        comment('{} {} {} {} {} {} {}'.format(kask, kbid, aski, bidi, best_profit,
               self.depths[kask]["asks"][aski]["price"],
               self.depths[kbid]["bids"][bidi]["price"]))
        return best_profit, best_volume, \
               self.depths[kask]["asks"][aski]["price"], \
               self.depths[kbid]["bids"][bidi]["price"], \
               best_w_buyprice, best_w_sellprice

    def arbitrage_opportunity(self, kask, ask, kbid, bid):
        perc = (bid["price"] - ask["price"]) / bid["price"] * 100
        comment('self.arbitrage_depth_opportunity')
        profit, volume, buyprice, sellprice, weighted_buyprice,\
            weighted_sellprice = self.arbitrage_depth_opportunity(kask, kbid)
        if volume == 0 or buyprice == 0:
            return
        perc2 = (1 - (volume - (profit / buyprice)) / volume) * 100
        for observer in self.observers:
            comment('observer.opportunity in {}'.format(observer))
            observer.opportunity(
                profit, volume, buyprice, kask, sellprice, kbid,
                perc2, weighted_buyprice, weighted_sellprice)

    def __get_market_depth(self, market, depths):
        depths[market.name] = market.get_depth()

    def update_depths(self):
        depths = {}
        futures = []
        for market in self.markets:
            futures.append(self.threadpool.submit(self.__get_market_depth,
                                                  market, depths))
        wait(futures, timeout=20)
        return depths

    def tickers(self):
        for market in self.markets:
            logging.verbose("ticker: " + market.name + " - " + str(
                market.get_ticker()))

    def replay_history(self, directory):
        import os
        import json
        import pprint
        files = os.listdir(directory)
        files.sort()
        for f in files:
            depths = json.load(open(directory + '/' + f, 'r'))
            self.depths = {}
            for market in self.market_names:
                if market in depths:
                    self.depths[market] = depths[market]
            self.tick()

    def tick(self):
        for observer in self.observers:
            observer.begin_opportunity_finder(self.depths)

        for kmarket1 in self.depths:
            for kmarket2 in self.depths:
                if kmarket1 == kmarket2:  # same market
                    continue
                market1 = self.depths[kmarket1]
                market2 = self.depths[kmarket2]
                if market1["asks"] and market2["bids"] \
                   and len(market1["asks"]) > 0 and len(market2["bids"]) > 0:
                    if float(market1["asks"][0]['price']) \
                       < float(market2["bids"][0]['price']):
                        self.arbitrage_opportunity(kmarket1, market1["asks"][0],
                                                   kmarket2, market2["bids"][0])

        for observer in self.observers:
            observer.end_opportunity_finder()

    def loop(self):
        while True:
            self.depths = self.update_depths()
            self.tickers()
            self.tick()
            time.sleep(config.refresh_rate)
