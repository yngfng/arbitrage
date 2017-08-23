import sys
sys.path.append('../')
import json
import time
import logging
from observers import observer
from fiatconverter import FiatConverter
import arbitrage

def config_log():
    level = logging.COMMENT = 9
    logging.addLevelName(logging.COMMENT, 'COMMENT')
    logging.basicConfig(format='%(asctime)s [%(levelname)s @%(module)-20s] %(message)s', level=level)
config_log()
comment = lambda msg: logging.getLogger(__name__).log(logging.COMMENT, msg)

class TestObserver(observer.Observer):
    def opportunity(self, profit, volume, buyprice, kask, sellprice, kbid,
                    perc, weighted_buyprice, weighted_sellprice):
        print("Time: %.3f" % profit)


def main():
    comment('initiate arbitrer')
    arbitrer = arbitrage.Arbitrer()
    comment('load depths')
    depths = arbitrer.depths = json.load(open("speed-test.json"))
    start_time = time.time()
    comment('initiate obs')
    testobs = TestObserver()
    arbitrer.observers = [testobs]
    comment('arbitrer.arbitrage_opportunity')
    arbitrer.tick()
    elapsed = time.time() - start_time
    comment("Time: %.3f" % elapsed)
    arbitrer.arbitrage_opportunity("BitstampUSD", depths["BitstampUSD"]["asks"][0],
                                   "MtGoxEUR", depths["MtGoxEUR"]["asks"][0])
    # FIXME: add asserts
    elapsed = time.time() - start_time - elapsed
    comment("Time: %.3f" % elapsed)


if __name__ == '__main__':
    main()
