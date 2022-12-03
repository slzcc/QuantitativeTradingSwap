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

def on_open(self):
    subscribe_message = {"method": "SUBSCRIBE","params": ["btcusdt@depth@1000ms"],"id": 1}
    ws.send(json.dumps(subscribe_message))
def on_message(self, message):
    print(message)
def on_close(self):
    print("closed connection")

class GridStrategy(Process):
    def __init__(self, key, secret, token, market=False):
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
        if not self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction), [])

        # 获取最新价格 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction), [])

        # 获取最新价格 eth/BTCUSDT多
        if not self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction), [])

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

        # 创建日志器对象
        ######################################## Logging __name__ #######################################
        self.logger = logging.getLogger(self.name)

        # 设置logger可输出日志级别范围
        self.logger.setLevel(logging.DEBUG)

        # 添加控制台handler，用于输出日志到控制台
        console_handler = logging.StreamHandler()
        # 日志输出到系统
        # console_handler = logging.StreamHandler(stream=None）
        # 添加日志文件handler，用于输出日志到文件中
        #file_handler = logging.FileHandler(filename='logs/{}.log'.format(self.name), encoding='UTF-8', when='H', interval=6, backupCount=4)
        file_handler = TimedRotatingFileHandler(filename='logs/{}.log'.format(self.name), encoding='UTF-8', when='H', interval=6, backupCount=4)

        # 将handler添加到日志器中
        #logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

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
        self.profit = arg_data['profit'] / 100
        self.min_profit = arg_data['min_profit'] / 100
        self.ratio = arg_data['ratio']

    def getWS(self):
        socket='wss://fstream.binance.com/ws'
        ws = websocket.WebSocketApp(socket, on_open=on_open, on_message=on_message)
        ws.run_forever()

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
        # 设置当前启动时间
        self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        self.logger.info('{} U本位开始运行 \t {} \t #################'.format(self.symbol, PublicModels.changeTime(time.time())))

        p1 = Process(target=getWS)
        p1.start()

        while True:
            time.sleep(1)
            print(1)

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'key': args.key, 'secret': args.secret, 'token': args.token}
    
    gs = GridStrategy(**conn_setting)
    gs.run()
    gs.join()
