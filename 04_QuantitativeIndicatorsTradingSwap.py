# 马丁微调, 设置浮亏补仓次数上限, 到达上限会挂上止盈单后启动下一轮新马丁
# 在浮盈时固定间隔加一倍底仓, 按回调率跟踪止盈, 暂定浮盈的20%，比如浮盈5%回撤至4%，可根据实际调整一个动态回调算法
# 该策略运行时长约2-3个月, 收益曲线不平稳, 实盘当时有4k+U, 1个月收益60%，从5w的饼做多到6w9, 后面持续做多, 在暴跌中, 该策略注定了吃灰的结局, 如果能看出较大的趋势波段, 此策略堪称优秀, 币本位食用更佳
import time
import json
import sys
import logging
import os
import numpy as np

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

class GridStrategy(Process):
    def __init__(self, symbol, key, secret, token, market=False):
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
        self.name = symbol              # 开单名称
        self.symbol = symbol[:-1]       # 获取对币种进行切割如 ETHUSDT多 取 ETHUSDT
        self.side = symbol[-1]          # 获取对币种进行切割如 ETHUSDT多 取 多
        self.read_conf(symbol)
        
        # 初始化 Redis 默认数据
        # timestamp default
        # 记录当前运行时间
        if not self.redisClient.getKey("{}_futures_t_start_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_t_start_{}".format(self.token, self.direction), time.time())
        # _last_order_time_ default
        # 记录上一次下单时间
        if not self.redisClient.getKey("{}_futures_last_order_time_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_last_order_time_{}".format(self.token, self.direction), 0)
        # 下单池
        if not self.redisClient.getKey("{}_futures_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_order_pool_{}".format(self.token, self.direction), 0)

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
        arg_data = json.load(open('conf/swapSymbol.json'))[symbol]
        self.price_precision = arg_data['price_precision']
        self.qty_precision = arg_data['qty_precision']
        self.min_qty = arg_data['min_qty']
        self.max_add_times = arg_data['max_add_times'] / 2
        self.profit = arg_data['profit'] / 100
        self.min_profit = arg_data['min_profit'] / 100
        self.add_rate = arg_data['add_rate'] / 100
        self.T = arg_data['T']
        self.position_times = arg_data['position_times']
        self.if_loss = arg_data['if_loss']
        self.order_interval = arg_data['order_interval']

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
        trade.set_leverage(self.symbol, self.position_times).json()
        # 设置当前启动时间
        self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        self.logger.info('{}/{} U本位开始运行 \t {} \t #################'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
        while True:
            try:
                # 获取 1m 时间的 k 线
                # Docs https://binance-docs.github.io/apidocs/spot/cn/#k
                """
                [
                  [
                    1499040000000,      // k线开盘时间
                    "0.01634790",       // 开盘价
                    "0.80000000",       // 最高价
                    "0.01575800",       // 最低价
                    "0.01577100",       // 收盘价(当前K线未结束的即为最新价)
                    "148976.11427815",  // 成交量
                    1499644799999,      // k线收盘时间
                    "2434.19055334",    // 成交额
                    308,                // 成交笔数
                    "1756.87402397",    // 主动买入成交量
                    "28.46694368",      // 主动买入成交额
                    "17928899.62484339" // 请忽略该参数
                  ]
                ]
                """
                klines = get_history_k(typ='futures', coin=self.symbol, T='1h', limit=500).json()
                close_price = list(map(lambda x: float(x[4]), klines))

                

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'symbol': args.symbol, 'key': args.key, 'secret': args.secret, 'token': args.token}
    
    p1 = Process(target=globalSetOrderIDStatus, args=(args.symbol, args.key, args.secret, args.token,))
    gs = GridStrategy(**conn_setting)
    p1.start()
    gs.run()
    gs.join()
    p1.join()
