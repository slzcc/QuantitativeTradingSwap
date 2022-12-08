#***********************************************
#
#      Filename: QuantitativeMASwap.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 量化系数交易
#
#        Create: 2022-12-08 10:08:32
# Last Modified: 2022-12-08 10:08:32
#
#***********************************************

import time
import json
import sys
import logging
import os
import numpy as np
import websocket
import talib

from utils.binance import tradeAPI
from utils.binance.getKlineData import *
from conf.settings import *
from utils.public import *
from utils import public as PublicModels
from utils.method import redisMethod
from utils.method import toolsMethod
from utils.method.toolsMethod import globalSetOrderIDStatus

from utils.QuantitativeTradingSwapUtils import command_line_args
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import Process
from decimal import Decimal
import numpy as np

redisClient = redisMethod.redisUtils()

# websocket.enableTrace(True)

class GridStrategy(Process):
    def __init__(self, symbol, key, secret, token):
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
        self.name = '{}_MA'.format(symbol)              # 开单名称
        self.symbol =  symbol
        self.direction = 'coefficient'
        # self.read_conf(self.symbol)

        # 初始化 Redis 默认数据
        # timestamp default
        # 记录当前运行时间
        if not self.redisClient.getKey("{}_futures_t_start_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_t_start_{}".format(self.token, self.direction), time.time())
        # _last_order_time_ default
        # 记录上一次下单时间
        if not self.redisClient.getKey("{}_futures_last_order_time_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_last_order_time_{}".format(self.token, self.direction), 0)

        # 如果日志目录不存在进行创建
        if not os.path.exists('logs'):
            os.mkdir('logs')

        # 创建日志器对象
        ######################################## Logging __name__ #######################################
        logger = logging.getLogger(self.name)

        # 设置logger可输出日志级别范围
        logger.setLevel(logging.DEBUG)

        # 添加控制台handler，用于输出日志到控制台
        console_handler = logging.StreamHandler()
        # 添加日志文件handler，用于输出日志到文件中
        file_handler = TimedRotatingFileHandler(filename='logs/{}.log'.format(self.name), encoding='UTF-8', when='H', interval=6, backupCount=4)

        # 将handler添加到日志器中
        logger.addHandler(file_handler)

        # 设置格式并赋予handler
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

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

    def _privateConversionDataType(self, value, dataType='string'):
        """
        转换数据类型
        :param value:    数据
        :param dataType: 转换的数据类型
        """
        res = value
        try:
            if dataType == "int":
                res = int(value)
            elif dataType == "float":
                res = float(value)
            elif dataType == "json_loads":
                res = json.loads(value)
            elif dataType == "json_dumps":
                res = json.dumps(value)
            elif dataType == "array":
                if type(value) == list:
                    res = np.asarray(value)
        except Exception as err:
            logger.error("调用 _privateConversionDataType 时异常错误, Value: {}, DataType: {}".format(value, dataType))
        return res

    def _privateRedisMethod(self, key, types="GET", value=None, datatype='string'):
        res = ""
        if types == "SET":
            res = self.redisClient.setKey("{}{}{}".format(self.token, key, self.direction), value)
        elif types == "GET":
            res = self.redisClient.getKey("{}{}{}".format(self.token, key, self.direction))
            if not dataType == "string":
                res = self._privateConversionDataType(res, datatype)
        return res

    def on_open_binance_symbol_kline(self, ws):
        subscribe_message = {"method": "SUBSCRIBE", "params": ["{}@kline_1m".format(self.symbol.lower())], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_symbol_kline(self, ws, message):
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self._privateRedisMethod(key="_futures_{}_present_price_".format(self.symbol.lower()), value=_message["k"]["c"], types="SET")

    def on_close(self):
        print("closed connection")

    def getBinanceSymbolKlineWS(self):
        while True:
            try:
                ws = websocket.WebSocketApp(FUTURE_WS, on_open=self.on_open_binance_symbol_kline, on_message=self.on_message_binance_symbol_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))

    def getBinanceSymbolHistoryKline(self, timestamp='1h', limit=500):
        klines = get_history_k(typ='futures', coin=self.symbol, T=timestamp, limit=limit).json()
        self._privateRedisMethod(key="_futures_{}_kline_".format(self.symbol.lower()), value=json.dumps(klines), types="SET")
        price_clone = list(map(lambda x: float(x[4]), klines))
        self._privateRedisMethod(key="_futures_{}_kline_price_clone_".format(self.symbol.lower()), value=json.dumps(price_clone), types="SET")
        price_array = np.asarray(price_clone)

        EMA5 = talib.EMA(price_array, 5)
        self._privateRedisMethod(key="_futures_{}_kline_EMA5_".format(self.symbol.lower()), value=json.dumps(EMA5.tolist()), types="SET")
        EMA10 = talib.EMA(price_array, 10)
        self._privateRedisMethod(key="_futures_{}_kline_EMA10_".format(self.symbol.lower()), value=json.dumps(EMA10.tolist()), types="SET")

        MA5 = talib.MA(price_array, 5)
        self._privateRedisMethod(key="_futures_{}_kline_MA5_".format(self.symbol.lower()), value=json.dumps(MA5.tolist()), types="SET")
        MA10 = talib.MA(price_array, 10)
        self._privateRedisMethod(key="_futures_{}_kline_MA10_".format(self.symbol.lower()), value=json.dumps(MA10.tolist()), types="SET")
        time.sleep(10)

    def run(self):
        # # 获取一个 Binance API 对象
        # trade = tradeAPI.TradeApi(self.key, self.secret)
        # # 更改持仓方式，默认单向
        # checkAccount = trade.change_side(False).json()
        # if "code" in checkAccount.keys():
        #     if checkAccount["code"] != -4059:
        #         raise AssertionError("账户凭证存在异常, 返回内容 {}, 请检查后继续! 可能犹豫超时导致的时间加密数据超出认证时间导致.".format(checkAccount))

        # # 变换逐全仓, 默认逐仓
        # trade.change_margintype(self.symbol, isolated=False).json()
        # # 调整开仓杠杆
        # trade.set_leverage(self.symbol, self.ratio).json()
        # # 设置当前启动时间
        # self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        # logger.info('{} U本位开始运行 \t {} \t #################'.format(self.symbol, PublicModels.changeTime(time.time())))

        p1 = Process(target=self.getBinanceSymbolKlineWS)
        p2 = Process(target=self.getBinanceSymbolHistoryKline)
        p1.start()
        p2.start()

        while True:
            logger.info("持续运行中!")
            time.sleep(0.3)
            
if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'key': args.key, 'secret': args.secret, 'token': args.token, 'symbol': args.symbol}
    
    gs = GridStrategy(**conn_setting)
    gs.run()
    gs.join()
