#***********************************************
#
#      Filename: QuantitativeCoefficientsSwap.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 量化系数交易
#
#        Create: 2022-10-31 17:11:32
# Last Modified: 2022-10-31 17:11:32
#
#***********************************************

import time
import json
import sys
import logging
import os
import numpy as np
import websocket

from utils.binance import tradeAPI
from utils.binance.getKlineData import *
from conf.settings import *
from utils.public import *
from utils import public as PublicModels
from utils.method import redisMethod
from utils.method import toolsMethod
from utils.method.toolsMethod import globalSetOrderIDStatus

from utils.QuantitativeCoefficientSwapUtils import command_line_args
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import Process
from decimal import Decimal

# 创建日志器对象
######################################## Logging __name__ #######################################
logger = logging.getLogger('ETHBTC')

# 设置logger可输出日志级别范围
logger.setLevel(logging.DEBUG)

# 添加控制台handler，用于输出日志到控制台
console_handler = logging.StreamHandler()
# 日志输出到系统
# console_handler = logging.StreamHandler(stream=None）
# 添加日志文件handler，用于输出日志到文件中
#file_handler = logging.FileHandler(filename='logs/{}.log'.format(self.name), encoding='UTF-8', when='H', interval=6, backupCount=4)
file_handler = TimedRotatingFileHandler(filename='logs/{}.log'.format('ETHBTC'), encoding='UTF-8', when='H', interval=6, backupCount=4)

# 将handler添加到日志器中
#logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 设置格式并赋予handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

redisClient = redisMethod.redisUtils()

# websocket.enableTrace(True)

class GridStrategy(Process):
    def __init__(self, key, secret, token):
        """
        :param symbol: BTCUSDT多
        :param key   : AccessKey
        :param secret: AccessSecret
        :param token : 当前程序身份
        """
        super().__init__()

        self.redisClient = redisMethod.redisUtils()  # redis 对象
        self.token = token              # redis key 前缀
        self.key = key                  # 用户凭证
        self.secret = secret            # 用户凭证
        self.name = 'ETHBTC'            # 开单名称
        self.symbol =  'ETHBTC'
        self.direction = 'coefficient'
        self.read_conf(self.symbol)

        # 初始化 Redis 默认数据
        # 获取最新价格 btc/usdt
        if not self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 btc/usdt
        if not self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 btc/usdt
        if not self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), '[]')

        # 获取最新价格 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), '[]')

        # 获取最新价格 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction), '[]')

        # timestamp default
        # 记录当前运行时间
        if not self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        # _last_order_time_ default
        # 记录上一次下单时间
        if not self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), 0)

        # 如果日志目录不存在进行创建
        if not os.path.exists('logs'):
            os.mkdir('logs')

    def read_conf(self, symbol):
        """
        获取开仓币种初始参数
        """
        arg_data = json.load(open('conf/coefficientSymbol.json'))[symbol]
        self.price_precision = arg_data['price_precision']
        self.min_qty = arg_data['min_qty']
        self.profit = arg_data['profit'] / 100
        self.min_profit = arg_data['min_profit'] / 100
        self.ratio = arg_data['ratio']

    def on_open_binance_btcusdt_kline(self, ws):
        subscribe_message = {"method": "SUBSCRIBE", "params": ["btcusdt@kline_1m"], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_btcusdt_kline(self, ws, message):
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self.redisClient.setKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction), _message["k"]["c"])

    def on_open_binance_ethusdt_kline(self, ws):
        subscribe_message = {"method": "SUBSCRIBE", "params": ["ethusdt@kline_1m"], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_ethusdt_kline(self, ws, message):
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self.redisClient.setKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction), _message["k"]["c"])

    def on_open_binance_ethbtc_kline(self, ws):
        subscribe_message = {"method": "SUBSCRIBE", "params": ["ethbtc@kline_1m"], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_ethbtc_kline(self, ws, message):
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self.redisClient.setKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction), _message["k"]["c"])

    def on_close(self):
        print("closed connection")

    def getBinanceBtcUsdtKlineWS(self):
        while True:
            try:
                ws = websocket.WebSocketApp(FUTURE_WS, on_open=self.on_open_binance_btcusdt_kline, on_message=self.on_message_binance_btcusdt_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))
    def getBinanceEthUsdtKlineWS(self):
        while True:
            try:
                ws = websocket.WebSocketApp(FUTURE_WS, on_open=self.on_open_binance_ethusdt_kline, on_message=self.on_message_binance_ethusdt_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))
    def getBinanceEthBtcKlineWS(self):
        while True:
            try:
                ws = websocket.WebSocketApp(SPOT_WS, on_open=self.on_open_binance_ethbtc_kline, on_message=self.on_message_binance_ethbtc_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))
    def run(self):
        # 获取一个 Binance API 对象
        trade = tradeAPI.TradeApi(self.key, self.secret)
        # 更改持仓方式，默认单向
        checkAccount = trade.change_side(False).json()
        if "code" in checkAccount.keys():
            if checkAccount["code"] != -4059:
                raise AssertionError("账户凭证存在异常, 返回内容 {}, 请检查后继续! 可能犹豫超时导致的时间加密数据超出认证时间导致.".format(checkAccount))

        # 变换逐全仓, 默认逐仓
        trade.change_margintype(self.symbol, isolated=False).json()
        # 调整开仓杠杆
        trade.set_leverage(self.symbol, self.ratio).json()
        # 设置当前启动时间
        self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        logger.info('{} U本位开始运行 \t {} \t #################'.format(self.symbol, PublicModels.changeTime(time.time())))

        p1 = Process(target=self.getBinanceBtcUsdtKlineWS)
        p2 = Process(target=self.getBinanceEthUsdtKlineWS)
        p3 = Process(target=self.getBinanceEthBtcKlineWS)
        p1.start()
        p2.start()
        p3.start()

        while True:
            time.sleep(1)
            # 判断下单池是否为空
            btc_usdt_order_pool = json.loads(self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)))
            eth_usdt_order_pool = json.loads(self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)))
            if len(btc_usdt_order_pool) == 0 and len(eth_usdt_order_pool) == 0:
                # 如果没有被下单则进行第一次下单
                ## BTC/USDT 开单(最小下单量 0.001)
                resOrder = trade.open_order('BTCUSDT', 'BUY', self.min_qty, price=None, positionSide='LONG').json()
                if not 'orderId' in resOrder.keys():
                    if resOrder['msg'] == 'Margin is insufficient.':
                        logger.info('%s 建仓失败, 可用金不足 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                    else:
                        logger.info('%s 建仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                    continue
                else:
                    logger.info('{} 建仓成功'.format('BTCUSDT'))
                    # 记录下单价格
                    self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
                    # 记录下单池
                    btc_usdt_order_pool.append(self.min_qty)
                    self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_order_pool))
                ## 基于 BTC 开仓数量，计算出 ETH 需要的开仓数量
                ## ETH/USDT 开单(最小下单量 0.004)
                _ethUsdtOrderQuantity = float(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction))) * self.min_qty / float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                ethUsdtOrderQuantity = float('%.3f' % _ethUsdtOrderQuantity)
                resOrder = trade.open_order('ETHUSDT', 'SELL', ethUsdtOrderQuantity, price=None, positionSide='SHORT').json()
                if not 'orderId' in resOrder.keys():
                    if resOrder['msg'] == 'Margin is insufficient.':
                        logger.info('%s 建仓失败, 可用金不足 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                    else:
                        logger.info('%s 建仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                    continue
                else:
                    logger.info('{} 建仓成功'.format('ETHUSDT'))
                    # 记录下单价格
                    self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                    # 记录下单池
                    eth_usdt_order_pool.append(self.min_qty)
                    self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_order_pool))
                # 记录下单时间
                self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                # ETHBTC
                ## 记录下单价格
                self.redisClient.setKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction),
                                        self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))
                ## 记录下单池
                self.redisClient.setKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction),
                                        self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))
            else:
                # 计算盈亏百分比
                ## BTC 当前价格
                btc_usdt_present_price = float(self.redisClient.getKey(
                    "{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
                ## BTC 最后下单价格
                btc_usdt_last_trade_price = float(self.redisClient.getKey(
                    "{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)))
                ## ETH 当前价格
                eth_usdt_present_price = float(self.redisClient.getKey(
                    "{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                ## ETH 最后下单价格
                eth_usdt_last_trade_price = float(self.redisClient.getKey(
                    "{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)))
                # 判定如果大于 profit 则进行清仓
                ## BTCUSDT 盈亏百分比
                btc_usdt_profi_loss = (btc_usdt_present_price - btc_usdt_last_trade_price) / btc_usdt_present_price * self.ratio * 100
                ## ETHUSDT 盈亏百分比
                eth_usdt_profi_loss = ((eth_usdt_present_price - eth_usdt_last_trade_price) / eth_usdt_present_price * self.ratio * 100)
                if (btc_usdt_profi_loss + eth_usdt_profi_loss) >= self.profit:
                    logger.info('准备清仓, 当前 BTCUSDT 盈损比例 {}, ETHUSDT 盈损比例 {}, 合计 {}'.format(btc_usdt_profi_loss,
                                                                                                eth_usdt_profi_loss,
                                                                                                btc_usdt_profi_loss + eth_usdt_profi_loss))
                    ## BTC/USDT 清仓
                    resOrder = trade.open_order('BTCUSDT', 'SELL', float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)))])), price=None, positionSide='LONG').json()
                    if not 'orderId' in resOrder.keys():
                        logger.info('%s 清仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                        continue
                    else:
                        logger.info('{} 清仓成功'.format('BTCUSDT'))
                        # 清除下单价格
                        self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)
                        # 清除下单池
                        self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), '[]')
                    ## ETH/USDT 清仓
                    resOrder = trade.open_order('ETHUSDT', 'BUY', float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)))])), price=None, positionSide='SHORT').json()
                    if not 'orderId' in resOrder.keys():
                        logger.info('%s 清仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                        continue
                    else:
                        logger.info('{} 清仓成功'.format('ETHUSDT'))
                        # 清除下单价格
                        self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)
                        # 清除下单池
                        self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), '[]')
                else:
                    logger.info('持续监听, 当前 BTCUSDT 盈损比例 {}, ETHUSDT 盈损比例 {}, 合计 {}'.format(btc_usdt_profi_loss, eth_usdt_profi_loss, btc_usdt_profi_loss + eth_usdt_profi_loss))

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'key': args.key, 'secret': args.secret, 'token': args.token}
    
    gs = GridStrategy(**conn_setting)
    gs.run()
    gs.join()
