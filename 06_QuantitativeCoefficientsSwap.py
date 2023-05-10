#***********************************************
#
#      Filename: QuantitativeCoefficientsSwap.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 量化系数交易
#                可基于 ETH/BTC 系数值判定开仓方向
#                05 的解耦版本, 默认单币当亏损到阀值后进入双币多空模式
#
#        Create: 2022-10-31 17:11:32
# Last Modified: 2023-05-05 11:12:33
#
#***********************************************

import time
import datetime
import json
import sys
import logging
import os
import numpy as np
import websocket
import pytz

from utils.binance import tradeAPI
from utils.binance.getKlineData import *
from conf.settings import *
from utils.public import *
from utils import public as PublicModels
from utils.method import redisMethod
from utils.method import toolsMethod
from utils.method.toolsMethod import globalSetOrderIDStatus
from threading import Thread
from utils.QuantitativeCoefficientSwapUtils import command_line_args
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import Process
from decimal import Decimal

def ShanghaiDateTime(sec):
    """
    设定 Log 北京时区
    """
    # if time.strftime('%z') == "+0800":
    #     return datetime.datetime.now().timetuple()
    # return (datetime.datetime.now() + datetime.timedelta(hours=8)).timetuple()
    return datetime.datetime.now(pytz.timezone('Asia/Shanghai')).timetuple()

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
# formatter.converter = ShanghaiDateTime

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
        self.symbol = 'ETHBTC'
        self.direction = 'coefficient'

        # 初始化 Redis 默认数据
        # 获取最新价格 btc/usdt
        if not self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 btc/usdt
        if not self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 btc/usdt (下单数量)
        if not self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), '[]')

        # 获取订单池 btc/usdt (订单号)
        ## 购买池
        if not self.redisClient.getKey("{}_futures_btc@usdt_buy_order_number_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_buy_order_number_pool_{}".format(self.token, self.direction), '[]')
        ## 出售池
        if not self.redisClient.getKey("{}_futures_btc@usdt_sell_order_number_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_sell_order_number_pool_{}".format(self.token, self.direction), '[]')

        # 获取最新价格 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 eth/usdt (下单数量)
        if not self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), '[]')

        # 获取订单池 eth/usdt (订单号)
        ## 购买池
        if not self.redisClient.getKey("{}_futures_eth@usdt_buy_order_number_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_buy_order_number_pool_{}".format(self.token, self.direction), '[]')
        ## 出售池
        if not self.redisClient.getKey("{}_futures_eth@usdt_sell_order_number_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_sell_order_number_pool_{}".format(self.token, self.direction), '[]')

        # 获取最新价格 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单价格 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction), 0.0)

        # 获取下单池 eth/btc
        if not self.redisClient.getKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction), '[]')

        # 停止下单 eth/usdt
        if not self.redisClient.getKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 0)

        # 停止下单 btc/usdt
        if not self.redisClient.getKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction), 0)

        # 停止下单（停止总下单）
        if not self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_order_pause_{}".format(self.token, self.direction), 'false')

        # 手续费(U)
        if not self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), 0.0)

        # 利润(U)
        if not self.redisClient.getKey("{}_all_order_profit_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_all_order_profit_{}".format(self.token, self.direction), 0.0)

        # 亏损(U)
        if not self.redisClient.getKey("{}_all_order_loss_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_all_order_loss_{}".format(self.token, self.direction), 0.0)

        # 强制平仓
        if not self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')

        # 趋势默认值, 当前价格高于此值时 ETH 开空, BTC 开多
        # 峰值 0.074, 2023-03-16 压力值 0.066
        if not self.redisClient.getKey("{}_long_short_trend_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_long_short_trend_{}".format(self.token, self.direction), '0.073')

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

        # 是否开启单币持仓模式
        # ETH/BTC
        # 默认 ETH
        if not self.redisClient.getKey("{}_open_single_currency_contract_trading_pair_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_open_single_currency_contract_trading_pair_{}".format(self.token, self.direction), 'ETH')

        # timestamp default
        # 记录当前运行时间
        if not self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        # _last_order_time_ default
        # 记录上一次下单时间
        if not self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), 0)

        # 最小开仓购买币的数量 Example: 0.004/BTC
        if not self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_min_qty_{}".format(self.token, self.direction), 0.004)

        # 总资产百分比 0 ~ 100
        # 当它为 0 时默认不开启
        # 当它其他是 1 ~ 100 任意数值时, 获取总资产百分比进行下单
        # 它启用后, 会覆盖 min_qty
        if not self.redisClient.getKey("{}_account_assets_total_percentage_qty_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_total_percentage_qty_{}".format(self.token, self.direction), 20)
        self.account_assets_total_percentage_qty = self.redisClient.getKey("{}_account_assets_total_percentage_qty_{}".format(self.token, self.direction))

        # 最大利润/止损, 使用时单位会 * 100, 作为 % 使用
        if not self.redisClient.getKey("{}_account_assets_profit_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_profit_{}".format(self.token, self.direction), 4)
        self.profit = int(self.redisClient.getKey("{}_account_assets_profit_{}".format(self.token, self.direction)))

        # 最小利润/止损
        if not self.redisClient.getKey("{}_account_assets_min_profit_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_min_profit_{}".format(self.token, self.direction), 0.04)
        self.min_profit = float(self.redisClient.getKey("{}_account_assets_min_profit_{}".format(self.token, self.direction)))

        # 开仓倍数(有BUG)
        if not self.redisClient.getKey("{}_account_assets_ratio_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_ratio_{}".format(self.token, self.direction), 10)
        self.ratio = int(self.redisClient.getKey("{}_account_assets_ratio_{}".format(self.token, self.direction)))

        # 亏损(容忍比例)
        if not self.redisClient.getKey("{}_account_assets_loss_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_loss_{}".format(self.token, self.direction), 0.05)
        self.loss = float(self.redisClient.getKey("{}_account_assets_loss_{}".format(self.token, self.direction)))

        # help default
        # Key 说明
        _help_text = """
        # BTC
        01、获取最新价格 btc/usdt: {0}_futures_btc@usdt_present_price_{1} 
        02、获取下单价格 btc/usdt: {0}_futures_btc@usdt_last_trade_price_{1} 
        03、获取下单池 btc/usdt (下单数量): {0}_futures_btc@usdt_order_pool_{1}

        # ETH
        04、获取最新价格 eth/usdt: {0}_futures_eth@usdt_present_price_{1}
        05、获取下单价格 eth/usdt: {0}_futures_eth@usdt_last_trade_price_{1}
        06、获取下单池 eth/usdt (下单数量): {0}_futures_eth@usdt_order_pool_{1}

        # ETH/BTC
        07、获取最新价格 eth/btc: {0}_spot_eth@btc_present_price_{1}
        08、获取下单价格 eth/btc: {0}_spot_eth@btc_last_trade_price_{1}
        09、获取下单池 eth/btc: {0}_spot_eth@btc_order_pool_{1}

        # 获取订单池 btc/usdt (订单号): 
        10、购买池: {0}_futures_btc@usdt_buy_order_number_pool_{1}
        11、出售池: {0}_futures_btc@usdt_sell_order_number_pool_{1}

        # 获取订单池 eth/usdt (订单号)
        12、购买池: {0}_futures_eth@usdt_buy_order_number_pool_{1}
        13、出售池: {0}_futures_eth@usdt_sell_order_number_pool_{1}
        
        14、停止下单: {0}_order_pause_{1}
        15、手续费(U): {0}_all_order_gas_{1}
        16、利润(U): {0}_all_order_profit_{1}
        17、亏损(U): {0}_all_order_loss_{1}
        18、强制平仓: {0}_forced_liquidation_{1}
        
        # 趋势默认值, 当前价格高于此值时 ETH 开空, BTC 开多
        # 峰值 0.076, 2023-04-28 压力值 0.073
        # 因单币模式主开 ETH, 需要对系数要求很高
        19、系数值: {0}_long_short_trend_{1}
        20、ETH 下单方向(BUY/SELL | LONG/SHORT): {0}_eth_order_direction_{1}
        21、BTC 下单方向(BUY/SELL | LONG/SHORT): {0}_btc_order_direction_{1}
        
        # 默认 false， 当等于 true 时, 则不会自动平单
        # 如果手动进行凭单请清空 redis 数据重启服务! 切记
        22、手动模式: _manual_mode_{1}
        
        # 多空方向, 由 {0}_long_short_trend_{1} key 判定得出, 默认为 1, 即: ETH 开空, BTC 开多
        # 值 0/1
        # 1(default): ETH 开空, BTC 开多
        # 0 : ETH 开多, BTC 开空
        23、多空方向: {0}_long_short_direction_{1}
        
        24、记录当前运行时间: {0}_t_start_{1}
        25、记录上一次下单时间: {0}_last_order_time_{1}
        
        26、记录是否开启单币持仓模式 (ETH/BTC): {0}_open_single_currency_contract_trading_pair_{1}
        
        27、最小开仓购买币的数量 Example: 0.004/BTC: {0}_account_assets_min_qty_{1}
        28、最大利润/止损, 使用时单位会 * 100, 作为 % 使用: {0}_account_assets_profit_{1}
        29、最小利润/止损 ---: {0}_account_assets_min_profit_{1}
        30、开仓倍数(有BUG): {0}_account_assets_ratio_{1}
        31、允许的亏损比例: {0}_account_assets_loss_{1}
        
        # 当进入清仓模式进行阻塞, 因清仓是异步执行
        # 0 是可以下单
        # 1 是不可下单
        32、停止下单 ETH/USDT: {0}_futures_eth@usdt_order_pause_{1}
        33、停止下单 BTC/USDT: {0}_futures_btc@usdt_order_pause_{1}
        
        # 总资产百分比 0 ~ 100
        # 当它为 0 时默认不开启
        # 当它其他是 1 ~ 100 任意数值时, 获取总资产百分比进行下单
        # 它启用后, 会覆盖 min_qty
        34、使用总资产百分比作为委托价格: {0}_account_assets_total_percentage_qty_{1}
        """.format(self.token, self.direction)
        self.redisClient.setKey("{}_help_{}".format(self.token, self.direction), _help_text)

        # 如果日志目录不存在进行创建
        if not os.path.exists('logs'):
            os.mkdir('logs')

    def on_open_binance_btcusdt_kline(self, ws):
        """
        websocket 获取 BTC/USDT 合约 1分钟 K 线
        """
        subscribe_message = {"method": "SUBSCRIBE", "params": ["btcusdt@kline_1m"], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_btcusdt_kline(self, ws, message):
        """
        对通过 websocket 获取的 BTC/USDT 合约数据获取最新价格存入 Redis 中
        """
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self.redisClient.setKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction), _message["k"]["c"])

    def on_open_binance_ethusdt_kline(self, ws):
        """
        websocket 获取 ETH/USDT 合约 1分钟 K 线
        """
        subscribe_message = {"method": "SUBSCRIBE", "params": ["ethusdt@kline_1m"], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_ethusdt_kline(self, ws, message):
        """
        对通过 websocket 获取的 ETH/USDT 合约数据获取最新价格存入 Redis 中
        """
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self.redisClient.setKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction), _message["k"]["c"])

    def on_open_binance_ethbtc_kline(self, ws):
        """
        websocket 获取 ETH/BTC 现货 1分钟 K 线
        """
        subscribe_message = {"method": "SUBSCRIBE", "params": ["ethbtc@kline_1m"], "id": 1}
        ws.send(json.dumps(subscribe_message))
    def on_message_binance_ethbtc_kline(self, ws, message):
        """
        对通过 websocket 获取的 ETH/BTC 现货数据获取最新价格存入 Redis 中
        """
        try:
            _message = json.loads(message)
        except Exception as err:
            _message = {}
            logger.error("异常错误: {}".format(err))
        if "e" in _message.keys():
            # 价格设置
            self.redisClient.setKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction), _message["k"]["c"])

    def on_close(self):
        """
        关闭 websocket 时执行
        """
        print("closed connection")

    def getBinanceBtcUsdtKlineWS(self):
        """
        BTC/USDT 子进程执行入口
        """
        while True:
            try:
                ws = websocket.WebSocketApp(FUTURE_WS, on_open=self.on_open_binance_btcusdt_kline, on_message=self.on_message_binance_btcusdt_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))
    def getBinanceEthUsdtKlineWS(self):
        """
        ETH/USDT 子进程执行入口
        """
        while True:
            try:
                ws = websocket.WebSocketApp(FUTURE_WS, on_open=self.on_open_binance_ethusdt_kline, on_message=self.on_message_binance_ethusdt_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))
    def getBinanceEthBtcKlineWS(self):
        """
        ETH/BTC 子进程执行入口
        """
        while True:
            try:
                ws = websocket.WebSocketApp(SPOT_WS, on_open=self.on_open_binance_ethbtc_kline, on_message=self.on_message_binance_ethbtc_kline)
                ws.run_forever()
            except Exception as err:
                logger.error("异常错误: {}".format(err))

    def checkOrder(self, trade, symbol, orderId):
        """
        检查订单当状态 NEW 返回 True, FILLED 返回 False
        """
        try:
            orderInfo = trade.check_order(symbol, orderId).json()

            # 判断是否成功获取订单信息
            # if not "updateTime" in orderInfo.keys():
            #     logger.warning("无法正常获取订单 updateTime, 对象数据: ".format(orderInfo))
            #     return True

            # 判断远程 API 当前 orderID 的状态 FILLED 为已经成功建仓 NEW 为委托单 EXPIRED 过期 CANCELED 取消订单
            if orderInfo["status"] == "FILLED":
                logger.info("检查订单 {} 状态正常".format(orderId))
                return False
            logger.warning("当前订单状态: {}".format(orderInfo))
            return True
        except Exception as err:
            logger.error("无法正常获取订单执行方法报错 {}, 对象数据: {}".format(err, orderId))
            return True

    def initializeOrderPrice(self, trade, asset='USDT', ratio=1):
        """
        初始化默认委托价格
        1、值 小于 3 时默认使用 _account_assets_min_qty_ 作为委托价格
        2、值 大于/等于 3 或获取账户总合约资产的百分比(USDT), 计算委托价格
        3、超过 100 默认使用 _account_assets_min_qty_ 作为委托价格

        当总资产计算得出不能满足 开仓 0.001/BTC 会向上补全 0.001/BTC 最小下单价格
        {'accountAlias': 'FzXqoCfWfWXqsRTi',
          'asset': 'USDT',
          'balance': '166.76892433',
          'crossWalletBalance': '166.76892433',
          'crossUnPnl': '-0.22548459',
          'availableBalance': '143.02746490',
          'maxWithdrawAmount': '143.02746490',
          'marginAvailable': True,
          'updateTime': 1683351333603}
        """
        self.account_assets_total_percentage_qty = int(self.redisClient.getKey("{}_account_assets_total_percentage_qty_{}".format(self.token, self.direction)))
        # 当此值为 0 使用 _account_assets_min_qty_ 参数为默认委托价格
        try:
            if self.account_assets_total_percentage_qty < 3:
                return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
            elif self.account_assets_total_percentage_qty >= 3 and self.account_assets_total_percentage_qty < 100:
                account_assets_list = trade.get_balance().json()
                for item in account_assets_list:
                    if item["asset"] == asset:
                        # 获取百分比资产
                        account_assets = Decimal(item["balance"]) * Decimal(self.account_assets_total_percentage_qty / 100)
                        # usdt 转换 币 真实数量，并做四舍五入
                        qty_number = round(account_assets / Decimal(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction))), 3)
                        # 需大于 btc 最小下单价格: 0.001
                        if qty_number < Decimal('0.001'):
                            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
                        # 判断是否大于 可用资产
                        qty_number_assets = qty_number * Decimal(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
                        available_assets = Decimal(item['availableBalance'])
                        if qty_number_assets < available_assets:
                            return float(qty_number) * ratio
                        else:
                            logger.error("初始化委托价格不能满足使用百分比总仓位, 因超出可用资产金额! 委托价格({}) > 可用资产({})".format(float(qty_number_assets), float(available_assets)))
                            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
        except:
            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))

    def ETH_StatisticalIncome(self):
        """
        计算 ETH 收益
        """
        ## ETH 当前价格
        eth_usdt_present_price = float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
        ## ETH 最后下单价格
        eth_usdt_last_trade_price = float(self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)))
        ## 获取 ETH 方向
        ETH_LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]

        # 判定如果大于 profit 则进行清仓
        if ETH_LONG_SHORT == 'LONG':
            ## ETHUSDT 盈亏百分比
            eth_usdt_profi_loss = (eth_usdt_present_price - eth_usdt_last_trade_price) / eth_usdt_present_price * self.ratio * 100
        else:
            ## ETHUSDT 盈亏百分比
            eth_usdt_profi_loss = (eth_usdt_last_trade_price - eth_usdt_present_price) / eth_usdt_present_price * self.ratio * 100
        return eth_usdt_profi_loss

    def BTC_StatisticalIncome(self):
        """
        计算 BTC 收益
        """
        ## BTC 当前价格
        btc_usdt_present_price = float(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
        ## BTC 最后下单价格
        btc_usdt_last_trade_price = float(self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)))
        ## 获取 BTC 方向
        BTC_LONG_SHORT = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[1]

        # 判定如果大于 profit 则进行清仓
        if BTC_LONG_SHORT == 'LONG':
            ## BTCUSDT 盈亏百分比
            btc_usdt_profi_loss = (btc_usdt_present_price - btc_usdt_last_trade_price) / btc_usdt_present_price * self.ratio * 100
        else:
            ## BTCUSDT 盈亏百分比
            btc_usdt_profi_loss = (btc_usdt_last_trade_price - btc_usdt_present_price) / btc_usdt_present_price * self.ratio * 100
        return btc_usdt_profi_loss

    def BTC_and_ETH_StatisticalIncome(self):
        """
        计算收益
        获取 BTC 和 ETH 的收益计算返回两个浮点数
        """
        return self.BTC_StatisticalIncome(), self.ETH_StatisticalIncome()

    def TrendShift(self, buy_sell):
        """
        买卖 转换
        用于买卖取反效果
        Example: BUY == SELL
        """
        if buy_sell == "BUY":
            return 'SELL'
        elif buy_sell == "SELL":
            return 'BUY'

    def BtcUsdtForcedLiquidation(self, trade):
        """
        BTC 清仓
        """
        try:
            ## 获取 BTC 方向
            BUY_SELL = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[0]
            LONG_SHORT = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[1]
            BUY_SELL = self.TrendShift(BUY_SELL)

            btc_order_pool = float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction)))]))
            ## BTC/USDT 清仓
            resOrder = trade.open_order('BTCUSDT', BUY_SELL, btc_order_pool, price=None, positionSide=LONG_SHORT).json()
            if not 'orderId' in resOrder.keys():
                logger.error('%s 清仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
            else:
                # 记录订单
                btc_usdt_sell_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_btc@usdt_sell_order_number_pool_{}".format(self.token, self.direction)))
                btc_usdt_sell_order_number_pool.append(resOrder["orderId"])
                # 检查订单是否完成, 否则阻塞
                while self.checkOrder(trade, 'BTCUSDT', resOrder["orderId"]):
                    time.sleep(1)
                    logger.warning('{} 清仓订单状态异常订单号 {} 订单状态 {}, {}/{}'.format('BTCUSDT', resOrder["orderId"], resOrder["status"], BUY_SELL, LONG_SHORT))
                self.redisClient.setKey("{}_futures_btc@usdt_sell_order_number_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_sell_order_number_pool))

                # 获取当前 gas
                all_order_gas = float(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                # 计算当前 BTC USDT 数量
                usdt_number = Decimal(btc_order_pool) * Decimal(float(self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction))))
                # 计算 gas 费用
                now_gas = (usdt_number * Decimal(0.0004)) + Decimal(all_order_gas)
                self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))

                # 清除下单价格
                self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)
                # 清除下单池
                self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), '[]')
                # 清除下单方向
                self.redisClient.setKey("{}_btc_order_direction_{}".format(self.token, self.direction), '')
                # 初始化单币模式
                self.initOpenSingleCurrencyContractTradingPair()
                # 开启下单模式
                self.redisClient.setKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction), 0)

                logger.info('{} 清仓成功, 卖出数量: {}, 等价 USDT: {:.2f}, GAS: {:.2f}'.format('BTCUSDT', btc_order_pool, float(usdt_number), float(now_gas)))
        except Exception as err:
            logger.error('{} 清仓异常错误: {}'.format('BTCUSDT', err))

    def EthUsdtForcedLiquidation(self, trade):
        """
        ETH 清仓
        """
        try:
            ## 获取 ETH 方向
            BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
            LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]
            BUY_SELL = self.TrendShift(BUY_SELL)

            eth_order_pool = float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction)))]))
            ## ETH/USDT 清仓
            resOrder = trade.open_order('ETHUSDT', BUY_SELL, eth_order_pool, price=None, positionSide=LONG_SHORT).json()
            if not 'orderId' in resOrder.keys():
                logger.error('%s 清仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
            else:
                # 记录订单
                eth_usdt_sell_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_eth@usdt_sell_order_number_pool_{}".format(self.token, self.direction)))
                eth_usdt_sell_order_number_pool.append(resOrder["orderId"])
                # 检查订单是否完成, 否则阻塞
                while self.checkOrder(trade, 'ETHUSDT', resOrder["orderId"]):
                    time.sleep(1)
                    logger.warning('{} 清仓订单状态异常订单号 {} 订单状态 {}, {}/{}'.format('ETHUSDT', resOrder["orderId"], resOrder["status"], BUY_SELL, LONG_SHORT))
                self.redisClient.setKey("{}_futures_eth@usdt_sell_order_number_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_sell_order_number_pool))

                # 获取当前 gas
                all_order_gas = float(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                # 计算当前 ETC USDT 数量
                usdt_number = Decimal(eth_order_pool) * Decimal(float(self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction))))
                # 计算 gas 费用
                now_gas = (usdt_number * Decimal(0.0004)) + Decimal(all_order_gas)
                self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))

                # 清除下单价格
                self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), 0.0)
                # 清除下单池
                self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), '[]')
                # 清除下单方向
                self.redisClient.setKey("{}_eth_order_direction_{}".format(self.token, self.direction), '')
                # 初始化单币模式
                self.initOpenSingleCurrencyContractTradingPair()
                # 开启下单模式
                self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 0)

                logger.info('{} 清仓成功, 卖出数量: {}, 等价 USDT: {:.2f}, GAS: {:.2f}'.format('ETHUSDT', eth_order_pool, float(usdt_number), float(now_gas)))
        except Exception as err:
            logger.error('{} 清仓异常错误: {}'.format('ETHUSDT', err))
        
    def LongShortTrend(self):
        """
        判断趋势
        当 ETH/BTC 的值低于 `_long_short_trend_` 的值(default) 时配置
        则表明, ETH 弱势需开多, BTC 强势需开空, 反之
        """

        while True:
            try:
                if float(self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction))) > float(self.redisClient.getKey("{}_long_short_trend_{}".format(self.token, self.direction))):
                    self.redisClient.setKey("{}_long_short_direction_{}".format(self.token, self.direction), '1')
                else:
                    self.redisClient.setKey("{}_long_short_direction_{}".format(self.token, self.direction), '0')
                time.sleep(5)
            except Exception as err:
                logger.error('{} 判断趋势异常: {}'.format('ETHBTC', err))

    def LongShortDirection(self, symbol):
        """
        判断下单方向
        BUY/SELL | LONG/SHORT
        """

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

    def initOpenSingleCurrencyContractTradingPair(self, symbol='ETH'):
        """
        初始化单币模式
        """
        self.redisClient.setKey("{}_open_single_currency_contract_trading_pair_{}".format(self.token, self.direction), symbol)

    def run(self):
        """
        主进程执行入口
        """
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
            time.sleep(0.3)

            # 当进入平仓模式阻止建仓
            if int(self.redisClient.getKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction))) == 1 or int(self.redisClient.getKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction))) == 1:
                logger.info("进入暂停建仓模式..")
                time.sleep(1)
                continue

            # 初始化变量值
            self.profit = int(self.redisClient.getKey("{}_account_assets_profit_{}".format(self.token, self.direction)))
            self.min_profit = float(self.redisClient.getKey("{}_account_assets_min_profit_{}".format(self.token, self.direction)))
            self.loss = float(self.redisClient.getKey("{}_account_assets_loss_{}".format(self.token, self.direction)))
            self.open_single_currency_contract_trading_pair = self.redisClient.getKey("{}_open_single_currency_contract_trading_pair_{}".format(self.token, self.direction))

            # 判断当前是否开启单币仓位模式
            if self.open_single_currency_contract_trading_pair:
                try:
                    time.sleep(0.3)
                    # 强制平仓
                    if self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)) == 'true':
                        logger.info('{} 强制平仓'.format('ETHUSDT'))

                        ## ETH/USDT 清仓
                        g2 = Process(target=self.EthUsdtForcedLiquidation, args=(trade,))
                        g2.start()

                        # 设置暂停建仓
                        self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)

                        # 恢复强制平仓配置
                        self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')

                        # 计算收益
                        eth_usdt_profi_loss = self.ETH_StatisticalIncome()
                        all_order_profit = Decimal(self.redisClient.getKey("{}_all_order_profit_{}".format(self.token, self.direction)))
                        now_profit = Decimal(eth_usdt_profi_loss) + all_order_profit
                        self.redisClient.setKey("{}_all_order_profit_{}".format(self.token, self.direction), float(now_profit))

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

                    # 如果订单中存在双币池, 且单币开关打开状态, 需要把单币开关进行关闭
                    if len(btc_usdt_order_pool) != 0 and len(eth_usdt_order_pool) != 0:
                        # 关闭单币模式
                        self.redisClient.setKey("{}_open_single_currency_contract_trading_pair_{}".format(self.token, self.direction), '')
                        continue

                    # 如果没有被下单则进行第一次下单
                    elif len(btc_usdt_order_pool) == 0 and len(eth_usdt_order_pool) == 0:
                        time.sleep(5)
                        # 停止下单
                        if self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)) == 'true':
                            logger.info('{} 停止下单状态'.format('BTCUSDT and ETHUSDT'))
                            time.sleep(5)
                            continue
                        # 获取最新委托价格值
                        self.min_qty = self.initializeOrderPrice(trade=trade, asset='USDT', ratio=self.ratio)

                        ## 基于 BTC 开仓数量，计算出 ETH 需要的开仓数量
                        ## ETH/USDT 开单(最小下单量 0.004)
                        _ethUsdtOrderQuantity = float(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction))) * self.min_qty / float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                        ethUsdtOrderQuantity = float('%.3f' % _ethUsdtOrderQuantity)

                        ## 获取 ETH 方向
                        BUY_SELL, LONG_SHORT = self.LongShortDirection('BTCUSDT')

                        logger.info('{} 准备建仓单币'.format('ETHUSDT'))
                        resOrder = trade.open_order('ETHUSDT', BUY_SELL, ethUsdtOrderQuantity, price=None, positionSide=LONG_SHORT).json()
                        if not 'orderId' in resOrder.keys():
                            if resOrder['msg'] == 'Margin is insufficient.':
                                logger.error('%s 建仓失败, 可用金不足 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                            else:
                                logger.error('%s 建仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                            continue
                        else:
                            logger.info('{} 建仓成功, 购买数量: {}, 订单返回值: {}'.format('ETHUSDT', ethUsdtOrderQuantity, resOrder))
                            # 记录订单
                            eth_usdt_buy_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_eth@usdt_buy_order_number_pool_{}".format(self.token, self.direction)))
                            eth_usdt_buy_order_number_pool.append(resOrder["orderId"])
                            self.redisClient.setKey("{}_futures_eth@usdt_buy_order_number_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_buy_order_number_pool))
                            # 记录下单价格
                            self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                            # 记录下单池
                            eth_usdt_order_pool.append(ethUsdtOrderQuantity)
                            self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_order_pool))
                            # 记录 ETH 下单方向
                            self.redisClient.setKey("{}_eth_order_direction_{}".format(self.token, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))
                            # 获取当前 gas
                            all_order_gas = Decimal(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                            # 计算当前 ETC USDT 数量
                            usdt_number = Decimal(ethUsdtOrderQuantity) * Decimal(self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)))
                            # 计算 gas 费用
                            now_gas = (usdt_number * Decimal(0.0004)) + all_order_gas
                            self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))
                            # 记录下单时间
                            self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                    else:
                        # 如果非第一次下单则进入此规则
                        ## 获取 ETH 方向
                        ETH_BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
                        ETH_LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]

                        # 计算收益
                        eth_usdt_profi_loss = self.ETH_StatisticalIncome()
                        logger.info('ETHUSDT 方向: {}/{}, 最新价格: {}, 系数: {}'.format(ETH_BUY_SELL, ETH_LONG_SHORT, float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction))), float(self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))))

                        # 判断收益
                        if (eth_usdt_profi_loss) >= (self.profit * 3):
                            logger.info('准备清仓单币, 当前 ETHUSDT 盈损比例 {}, 合计 {}'.format(eth_usdt_profi_loss, eth_usdt_profi_loss))
                            ## ETH/USDT 清仓
                            g2 = Process(target=self.EthUsdtForcedLiquidation, args=(trade,))
                            g2.start()

                            # 设置暂停建仓
                            self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)

                            # 计算收益
                            all_order_profit = Decimal(self.redisClient.getKey("{}_all_order_profit_{}".format(self.token, self.direction)))
                            now_profit = Decimal(eth_usdt_profi_loss) + all_order_profit
                            self.redisClient.setKey("{}_all_order_profit_{}".format(self.token, self.direction), float(now_profit))

                        elif eth_usdt_profi_loss <= -(self.loss * 100):
                            """
                            当前收益 <= 容忍损失
                            进行对冲开单
                            """
                            # 获取最新委托价格值
                            self.min_qty = self.initializeOrderPrice(trade=trade, asset='USDT', ratio=self.ratio)

                            ## 获取 BTC 方向
                            BUY_SELL = 'SELL' if ETH_BUY_SELL == 'BUY' else 'BUY'
                            LONG_SHORT = 'SHORT' if ETH_LONG_SHORT == 'LONG' else 'LONG'

                            ## BTC/USDT 开单(最小下单量 0.001)
                            logger.info('{} 准备建仓 单币转双币'.format('BTCUSDT'))
                            resOrder = trade.open_order('BTCUSDT', BUY_SELL, self.min_qty, price=None, positionSide=LONG_SHORT).json()
                            if not 'orderId' in resOrder.keys():
                                if resOrder['msg'] == 'Margin is insufficient.':
                                    logger.error('%s 建仓失败, 可用金不足 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                                else:
                                    logger.error('%s 建仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                                continue
                            else:
                                logger.info('{} 建仓成功, 购买数量: {} 订单返回值: {}'.format('BTCUSDT', self.min_qty, resOrder))
                                # 记录订单
                                btc_usdt_buy_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_btc@usdt_buy_order_number_pool_{}".format(self.token, self.direction)))
                                btc_usdt_buy_order_number_pool.append(resOrder["orderId"])
                                self.redisClient.setKey("{}_futures_btc@usdt_buy_order_number_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_buy_order_number_pool))
                                # 记录下单价格
                                self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
                                # 记录下单池
                                btc_usdt_order_pool.append(self.min_qty)
                                self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_order_pool))
                                # 记录 BTC 下单方向
                                self.redisClient.setKey("{}_btc_order_direction_{}".format(self.token, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))
                                # 获取当前 gas
                                all_order_gas = Decimal(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                                # 计算当前 BTC USDT 数量
                                usdt_number = Decimal(self.min_qty) * Decimal(self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)))
                                # 计算 gas 费用
                                now_gas = (usdt_number * Decimal(0.0004)) + all_order_gas
                                self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))
                                # 记录下单时间
                                self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                                # 关闭单币模式
                                self.redisClient.setKey("{}_open_single_currency_contract_trading_pair_{}".format(self.token, self.direction), '')
                        else:
                            logger.info('持续监听, ETHUSDT 盈损比例 {}, 下单价格: {}'.format(eth_usdt_profi_loss, float(self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)))))

                except Exception as err:
                    logger.error('{} 单币主逻辑异常错误: {}'.format('ETHBTC', err))
            else:
                try:
                    time.sleep(0.3)
                    # 强制平仓
                    if self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)) == 'true':
                        logger.info('{} 强制平仓'.format('BTCUSDT'))

                        ## BTC/USDT 清仓
                        g1 = Process(target=self.BtcUsdtForcedLiquidation, args=(trade,))
                        ## ETH/USDT 清仓
                        g2 = Process(target=self.EthUsdtForcedLiquidation, args=(trade,))

                        g1.start()
                        g2.start()

                        # 设置暂停建仓
                        self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)
                        self.redisClient.setKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction), 1)

                        # 恢复强制平仓配置
                        self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')

                        # 计算收益
                        btc_usdt_profi_loss, eth_usdt_profi_loss = self.BTC_and_ETH_StatisticalIncome()
                        all_order_profit = Decimal(self.redisClient.getKey("{}_all_order_profit_{}".format(self.token, self.direction)))
                        now_profit = Decimal(btc_usdt_profi_loss + eth_usdt_profi_loss) + all_order_profit
                        self.redisClient.setKey("{}_all_order_profit_{}".format(self.token, self.direction), float(now_profit))

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
                        time.sleep(5)
                        # 获取最新委托价格值
                        self.min_qty = self.initializeOrderPrice(trade=trade, asset='USDT', ratio=self.ratio)

                        # 停止下单
                        if self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)) == 'true':
                            logger.info('{} 停止下单状态'.format('BTCUSDT and ETHUSDT'))
                            time.sleep(5)
                            continue
                        else:
                            ## 获取 BTC 方向
                            BUY_SELL, LONG_SHORT = self.LongShortDirection('BTCUSDT')
                            ## BTC/USDT 开单(最小下单量 0.001)
                            logger.info('{} 准备建仓双币'.format('BTCUSDT'))
                            resOrder = trade.open_order('BTCUSDT', BUY_SELL, self.min_qty, price=None, positionSide=LONG_SHORT).json()
                            if not 'orderId' in resOrder.keys():
                                if resOrder['msg'] == 'Margin is insufficient.':
                                    logger.error('%s 建仓失败, 可用金不足 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                                else:
                                    logger.error('%s 建仓失败 \t %s \t %s' % ('BTCUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                                continue
                            else:
                                logger.info('{} 建仓成功, 购买数量: {} 订单返回值: {}'.format('BTCUSDT', self.min_qty, resOrder))
                                # 记录订单
                                btc_usdt_buy_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_btc@usdt_buy_order_number_pool_{}".format(self.token, self.direction)))
                                btc_usdt_buy_order_number_pool.append(resOrder["orderId"])
                                self.redisClient.setKey("{}_futures_btc@usdt_buy_order_number_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_buy_order_number_pool))
                                # 记录下单价格
                                self.redisClient.setKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)))
                                # 记录下单池
                                btc_usdt_order_pool.append(self.min_qty)
                                self.redisClient.setKey("{}_futures_btc@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(btc_usdt_order_pool))
                                # 记录 BTC 下单方向
                                self.redisClient.setKey("{}_btc_order_direction_{}".format(self.token, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))
                                # 获取当前 gas
                                all_order_gas = Decimal(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                                # 计算当前 BTC USDT 数量
                                usdt_number = Decimal(self.min_qty) * Decimal(self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)))
                                # 计算 gas 费用
                                now_gas = (usdt_number * Decimal(0.0004)) + all_order_gas
                                self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))

                            ## 基于 BTC 开仓数量，计算出 ETH 需要的开仓数量
                            ## ETH/USDT 开单(最小下单量 0.004)
                            _ethUsdtOrderQuantity = float(self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction))) * self.min_qty / float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                            ethUsdtOrderQuantity = float('%.3f' % _ethUsdtOrderQuantity)

                            ## 获取 ETH 方向
                            # BUY_SELL, LONG_SHORT = self.LongShortDirection('ETHUSDT')
                            ## 获取 BTC 方向
                            BUY_SELL = 'SELL' if BUY_SELL == 'BUY' else 'BUY'
                            LONG_SHORT = 'SHORT' if LONG_SHORT == 'LONG' else 'LONG'

                            logger.info('{} 准备建仓双币'.format('ETHUSDT'))
                            resOrder = trade.open_order('ETHUSDT', BUY_SELL, ethUsdtOrderQuantity, price=None, positionSide=LONG_SHORT).json()
                            if not 'orderId' in resOrder.keys():
                                if resOrder['msg'] == 'Margin is insufficient.':
                                    logger.error('%s 建仓失败, 可用金不足 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                                else:
                                    logger.error('%s 建仓失败 \t %s \t %s' % ('ETHUSDT', str(resOrder), PublicModels.changeTime(time.time())))
                                continue
                            else:
                                logger.info('{} 建仓成功, 购买数量: {}, 订单返回值: {}'.format('ETHUSDT', ethUsdtOrderQuantity, resOrder))
                                # 记录订单
                                eth_usdt_buy_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_eth@usdt_buy_order_number_pool_{}".format(self.token, self.direction)))
                                eth_usdt_buy_order_number_pool.append(resOrder["orderId"])
                                self.redisClient.setKey("{}_futures_eth@usdt_buy_order_number_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_buy_order_number_pool))
                                # 记录下单价格
                                self.redisClient.setKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction)))
                                # 记录下单池
                                eth_usdt_order_pool.append(ethUsdtOrderQuantity)
                                self.redisClient.setKey("{}_futures_eth@usdt_order_pool_{}".format(self.token, self.direction), json.dumps(eth_usdt_order_pool))
                                # 记录 ETH 下单方向
                                self.redisClient.setKey("{}_eth_order_direction_{}".format(self.token, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))
                                # 获取当前 gas
                                all_order_gas = Decimal(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                                # 计算当前 ETC USDT 数量
                                usdt_number = Decimal(ethUsdtOrderQuantity) * Decimal(self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)))
                                # 计算 gas 费用
                                now_gas = (usdt_number * Decimal(0.0004)) + all_order_gas
                                self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))

                        # 记录下单时间
                        self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                        # ETHBTC
                        ## 记录下单价格
                        self.redisClient.setKey("{}_spot_eth@btc_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))
                        ## 记录下单池
                        eth_btc_order_pool = json.loads(self.redisClient.getKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction)))
                        eth_btc_order_pool.append(self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))
                        self.redisClient.setKey("{}_spot_eth@btc_order_pool_{}".format(self.token, self.direction), json.dumps(eth_btc_order_pool))

                    else:
                        ## 获取 ETH 方向
                        ETH_BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
                        ETH_LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]
                        ## 获取 BTC 方向
                        BTC_BUY_SELL = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[0]
                        BTC_LONG_SHORT = self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)).split("|")[1]

                        # 计算收益
                        btc_usdt_profi_loss, eth_usdt_profi_loss = self.BTC_and_ETH_StatisticalIncome()
                        logger.info('当前 BTCUSDT 方向: {}/{} 最新价格: {}, ETHUSDT 方向: {}/{} 最新价格: {}'.format(BTC_BUY_SELL, BTC_LONG_SHORT, self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)), ETH_BUY_SELL, ETH_LONG_SHORT, self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction))))

                        if (btc_usdt_profi_loss + eth_usdt_profi_loss) >= self.profit:
                            logger.info('准备清仓双币, 当前 BTCUSDT 盈损比例 {:.2f}, ETHUSDT 盈损比例 {:.2f}, 合计 {:.2f}'.format(btc_usdt_profi_loss, eth_usdt_profi_loss, btc_usdt_profi_loss + eth_usdt_profi_loss))
                            ## BTC/USDT 清仓
                            g1 = Process(target=self.BtcUsdtForcedLiquidation, args=(trade,))
                            ## ETH/USDT 清仓
                            g2 = Process(target=self.EthUsdtForcedLiquidation, args=(trade,))

                            g1.start()
                            g2.start()

                            # 设置暂停建仓
                            self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)
                            self.redisClient.setKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction), 1)

                            # 计算收益
                            all_order_profit = Decimal(self.redisClient.getKey("{}_all_order_profit_{}".format(self.token, self.direction)))
                            now_profit = Decimal(btc_usdt_profi_loss + eth_usdt_profi_loss) + all_order_profit
                            self.redisClient.setKey("{}_all_order_profit_{}".format(self.token, self.direction), float(now_profit))

                        else:
                            logger.info('持续监听, 当前 BTCUSDT 仓位价格: {} 盈损比例 {:.2f}, ETHUSDT 仓位价格: {} 盈损比例 {:.2f}, 合计 {:.2f}'.format(self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)), btc_usdt_profi_loss, self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)), eth_usdt_profi_loss, (btc_usdt_profi_loss + eth_usdt_profi_loss)))
                except Exception as err:
                    logger.error('{} 双币主逻辑异常错误: {}'.format('ETHBTC', err))

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'key': args.key, 'secret': args.secret, 'token': args.token}
    
    gs = GridStrategy(**conn_setting)
    gs.run()
    gs.join()
