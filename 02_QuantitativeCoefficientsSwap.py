#***********************************************
#
#      Filename: QuantitativeCoefficientsSwap.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 量化系数交易
#
#        Create: 2022-10-31 17:11:32
# Last Modified: 2023-03-15 11:12:33
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

def BeiJingDateTime(sec):
    """
    设定北京时区
    """
    if time.strftime('%z') == "+0800":
        return datetime.datetime.now().timetuple()
    return (datetime.datetime.now() + datetime.timedelta(hours=8)).timetuple()

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
# 设置日志时区
formatter.converter = BeiJingDateTime

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
        
        # 停止下单
        if not self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_order_pause_{}".format(self.token, self.direction), 'false')

        # 强制平仓
        if not self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')

        # 趋势默认值, 当前价格高于此值时 ETH 开空, BTC 开多
        if not self.redisClient.getKey("{}_long_short_trend_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_long_short_trend_{}".format(self.token, self.direction), '0.07')

        # ETH 下单方向
        # BUY/SELL | LONG/SHORT
        if not self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_eth_order_direction_{}".format(self.token, self.direction), 'SELL|SHORT')

        # BTC 下单方向
        # BUY/SELL | LONG/SHORT
        if not self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_btc_order_direction_{}".format(self.token, self.direction), 'BUY|LONG')

        # 手动模式
        # 默认 false， 当等于 true 时, 则不会自动平单
        # 如果手动进行凭单请清空 redis 数据重启服务! 切记
        if not self.redisClient.getKey("{}_manual_mode_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_manual_mode_{}".format(self.token, self.direction), 'false')

        # 多空方向, 由 _long_short_trend_ key 判定得出, 默认为 1, 即: ETH 开空, BTC 开多
        # 值 0/1
        # 1(default): ETH 开空, BTC 开多
        # 0 : ETH 开多, BTC 开空
        if not self.redisClient.getKey("{}_long_short_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_long_short_direction_{}".format(self.token, self.direction), '1')

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
        self.profit = arg_data['profit']
        self.min_profit = arg_data['min_profit']
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

    # BTC 清仓
    def BtcUsdtForcedLiquidation(self, trade):
        try:
            ## 获取 BTC 方向
            BUY_SELL = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[0]
            LONG_SHORT = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[1]

            ## BTC/USDT 清仓
            resOrder = trade.open_order('BTCUSDT', BUY_SELL, float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)))])), price=None, positionSide=LONG_SHORT).json()
            if not 'orderId' in resOrder.keys():
                logger.error('%s 清仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
            else:
                logger.info('{} 清仓成功, 卖出数量: {}'.format('BTCUSDT', float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)))]))))
                # 清除下单价格
                self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)
                # 清除下单池
                self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), '[]')
        except Exception as err:
            logger.error('{} BTC 清仓异常错误: {}'.format('BTCUSDT', err))

    # ETH 清仓
    def EthUsdtForcedLiquidation(self, trade):
        try:
            ## 获取 ETH 方向
            BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
            LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]

            ## ETH/USDT 清仓
            resOrder = trade.open_order('ETHUSDT', BUY_SELL, float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)))])), price=None, positionSide=LONG_SHORT).json()
            if not 'orderId' in resOrder.keys():
                logger.error('%s 清仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
            else:
                logger.info('{} 清仓成功, 卖出数量: {}'.format('ETHUSDT', float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)))]))))
                # 清除下单价格
                self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)
                # 清除下单池
                self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), '[]')
        except Exception as err:
            logger.error('{} ETH 清仓异常错误: {}'.format('ETHUSDT', err))
        
    # 判断趋势
    def LongShortTrend(self):
        # 当 ETH/BTC 的值低于 0.07(default) 时配置
        # 则表明, ETH 弱势需开多, BTC 强势需开空, 反之
        while True:
            try:
                if float(self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction))) > float(self.redisClient.getKey("{}_long_short_trend_{}".format(self.token, self.direction))):
                    self.redisClient.setKey("{}_long_short_direction_{}".format(self.token, self.direction), '1')
                else:
                    self.redisClient.setKey("{}_long_short_direction_{}".format(self.token, self.direction), '0')
                time.sleep(5)
            except Exception as err:
                logger.error('{} 判断趋势异常: {}'.format('ETHBTC', err))

    # 判断下单方向
    # BUY/SELL | LONG/SHORT
    def LongShortDirection(self, symbol):
        if symbol == "BTCUSDT":
            if int(self.redisClient.getKey("{}_long_short_direction_{}".format(self.token, self.direction))) == 1:
                return 'BUY', 'LONG'
            elif int(self.redisClient.getKey("{}_long_short_direction_{}".format(self.token, self.direction))) == 0:
                return 'SELL', 'SHORT'
            else:
                return 'BUY', 'LONG'
        elif symbol == "ETHUSDT":
            if int(self.redisClient.getKey("{}_long_short_direction_{}".format(self.token, self.direction))) == 1:
                return 'SELL', 'SHORT'
            elif int(self.redisClient.getKey("{}_long_short_direction_{}".format(self.token, self.direction))) == 0:
                return 'BUY', 'LONG'
            else:
                return 'SELL', 'SHORT'

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

        # 新进程, 获取 BTC/USDT 价格
        p1 = Process(target=self.getBinanceBtcUsdtKlineWS)
        # 新进程, 获取 ETH/USDT 价格
        p2 = Process(target=self.getBinanceEthUsdtKlineWS)
        # 新进程, 获取 ETH/BTC 价格
        p3 = Process(target=self.getBinanceEthBtcKlineWS)
        # 判断方向
        p4 = Process(target=self.LongShortTrend)
        p1.start()
        p2.start()
        p3.start()
        p4.start()

        while True:
            try:
                time.sleep(0.3)
                # 强制平仓
                if self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)) == 'true':
                    logger.info('{} 强制平仓'.format('BTCUSDT'))
                    ## BTC/USDT 清仓
                    self.BtcUsdtForcedLiquidation(trade)
                    ## ETH/USDT 清仓
                    self.EthUsdtForcedLiquidation(trade)
                    self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')
                    time.sleep(5)
                    continue

                # 手动模式
                if self.redisClient.getKey("{}_manual_mode_{}".format(self.token, self.direction)) == 'true':
                    logger.info('{} 开启手动模式'.format('ETHBTC'))
                    time.sleep(5)
                    continue

                # 判断下单池是否为空
                btc_usdt_order_pool = json.loads(self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)))
                eth_usdt_order_pool = json.loads(self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)))
                # 如果没有被下单则进行第一次下单
                if len(btc_usdt_order_pool) == 0 and len(eth_usdt_order_pool) == 0:
                    # 停止下单
                    if self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)) == 'true':
                        logger.info('{} 停止下单状态'.format('BTCUSDT and ETHUSDT'))
                        time.sleep(5)
                        continue
                    else:
                        ## 获取 BTC 方向
                        BUY_SELL, LONG_SHORT = self.LongShortDirection('BTCUSDT')
                        ## BTC/USDT 开单(最小下单量 0.001)
                        logger.info('{} 准备建仓'.format('BTCUSDT'))
                        resOrder = trade.open_order('BTCUSDT', BUY_SELL, self.min_qty, price=None, positionSide=LONG_SHORT).json()
                        if not 'orderId' in resOrder.keys():
                            if resOrder['msg'] == 'Margin is insufficient.':
                                logger.error('%s 建仓失败, 可用金不足 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                            else:
                                logger.error('%s 建仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                            continue
                        else:
                            logger.info('{} 建仓成功, 购买数量: {}'.format('BTCUSDT', self.min_qty))
                            # 记录下单价格
                            self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
                            # 记录下单池
                            btc_usdt_order_pool.append(self.min_qty)
                            self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_order_pool))
                            # 记录 BTC 下单方向
                            self.redisClient.setKey("{}_btc_order_direction_{}".format(self.token, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))

                        ## 基于 BTC 开仓数量，计算出 ETH 需要的开仓数量
                        ## ETH/USDT 开单(最小下单量 0.004)
                        _ethUsdtOrderQuantity = float(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction))) * self.min_qty / float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                        ethUsdtOrderQuantity = float('%.3f' % _ethUsdtOrderQuantity)

                        ## 获取 ETH 方向
                        BUY_SELL, LONG_SHORT = self.LongShortDirection('ETHUSDT')

                        logger.info('{} 准备建仓'.format('ETHUSDT'))
                        resOrder = trade.open_order('ETHUSDT', BUY_SELL, ethUsdtOrderQuantity, price=None, positionSide=LONG_SHORT).json()
                        if not 'orderId' in resOrder.keys():
                            if resOrder['msg'] == 'Margin is insufficient.':
                                logger.error('%s 建仓失败, 可用金不足 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                            else:
                                logger.error('%s 建仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                            continue
                        else:
                            logger.info('{} 建仓成功, 购买数量: {}'.format('ETHUSDT', ethUsdtOrderQuantity))
                            # 记录下单价格
                            self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                            # 记录下单池
                            eth_usdt_order_pool.append(ethUsdtOrderQuantity)
                            self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_order_pool))
                            # 记录 ETH 下单方向
                            self.redisClient.setKey("{}_eth_order_direction_{}".format(self.token, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))

                    # 记录下单时间
                    self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                    # ETHBTC
                    ## 记录下单价格
                    self.redisClient.setKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction),
                                            self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))
                    ## 记录下单池
                    eth_btc_order_pool = json.loads(self.redisClient.getKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction)))
                    eth_btc_order_pool.append(self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))
                    self.redisClient.setKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction), json.dumps(eth_btc_order_pool))

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

                    ## 获取 ETH 方向
                    ETH_BUY_SELL, ETH_LONG_SHORT = self.LongShortDirection('ETHUSDT')
                    ## 获取 BTC 方向
                    BTC_BUY_SELL, BTC_LONG_SHORT = self.LongShortDirection('BTCUSDT')

                    # 判定如果大于 profit 则进行清仓
                    if BTC_LONG_SHORT == 'LONG':
                        ## BTCUSDT 盈亏百分比
                        btc_usdt_profi_loss = (btc_usdt_present_price - btc_usdt_last_trade_price) / btc_usdt_present_price * self.ratio * 100
                        ## ETHUSDT 盈亏百分比
                        eth_usdt_profi_loss = (eth_usdt_last_trade_price - eth_usdt_present_price) / eth_usdt_present_price * self.ratio * 100
                    elif ETH_LONG_SHORT == 'LONG':
                        ## BTCUSDT 盈亏百分比
                        btc_usdt_profi_loss = (btc_usdt_last_trade_price - btc_usdt_present_price) / btc_usdt_present_price * self.ratio * 100
                        ## ETHUSDT 盈亏百分比
                        eth_usdt_profi_loss = (eth_usdt_present_price - eth_usdt_last_trade_price) / eth_usdt_present_price * self.ratio * 100

                    logger.info('当前 BTCUSDT 方向: {}/{}, ETHUSDT 方向: {}/{}'.format(BTC_BUY_SELL, BTC_LONG_SHORT, ETH_BUY_SELL, ETH_LONG_SHORT))

                    if (btc_usdt_profi_loss + eth_usdt_profi_loss) >= self.profit:
                        logger.info('准备清仓, 当前 BTCUSDT 盈损比例 {}, ETHUSDT 盈损比例 {}, 合计 {}'.format(btc_usdt_profi_loss,
                                                                                                    eth_usdt_profi_loss,
                                                                                                    btc_usdt_profi_loss + eth_usdt_profi_loss))
                        ## BTC/USDT 清仓
                        self.BtcUsdtForcedLiquidation(trade)
                        ## ETH/USDT 清仓
                        self.EthUsdtForcedLiquidation(trade)
                    else:
                        logger.info('持续监听, 当前 BTCUSDT 盈损比例 {}, ETHUSDT 盈损比例 {}, 合计 {}'.format(btc_usdt_profi_loss, eth_usdt_profi_loss, btc_usdt_profi_loss + eth_usdt_profi_loss))
            except Exception as err:
                logger.error('{} 主逻辑异常错误: {}'.format('ETHBTC', err))

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'key': args.key, 'secret': args.secret, 'token': args.token}
    
    gs = GridStrategy(**conn_setting)
    gs.run()
    gs.join()
