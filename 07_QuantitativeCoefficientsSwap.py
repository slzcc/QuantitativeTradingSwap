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

class GridStrategy(Process):
    def __init__(self, key, secret, token, redis_host, redis_port, redis_db, redis_auth):
        """
        :param symbol: BTCUSDT多
        :param key   : AccessKey
        :param secret: AccessSecret
        :param token : 当前程序身份
        """
        super().__init__()

        self.redisClient = redisMethod.redisUtils(host=redis_host, port=redis_port, db=redis_db, auth=redis_auth)  # redis 对象
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
        # 峰值 0.074, 2023-05-24 压力值 0.0677
        if not self.redisClient.getKey("{}_long_short_trend_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_long_short_trend_{}".format(self.token, self.direction), '0.0677')

        # ETH 下单方向
        # BUY/SELL | LONG/SHORT
        if not self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_eth_order_direction_{}".format(self.token, self.direction), '')

        # BTC 下单方向
        # BUY/SELL | LONG/SHORT
        if not self.redisClient.getKey("{}_btc_order_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_btc_order_direction_{}".format(self.token, self.direction), '')

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
        if not self.redisClient.getKey("{}_open_single_coin_contract_trading_pair_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_open_single_coin_contract_trading_pair_{}".format(self.token, self.direction), 'ETH')

        # timestamp default
        # 记录当前运行时间
        if not self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_t_start_{}".format(self.token, self.direction), time.time())
        # _last_order_time_ default
        # 记录上一次下单时间
        if not self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), 0)

        # 最小开仓购买币的数量 Example: 200/USDT
        if not self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_min_qty_{}".format(self.token, self.direction), 200)

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

        # 开仓倍数(杠該)
        if not self.redisClient.getKey("{}_account_assets_ratio_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_ratio_{}".format(self.token, self.direction), 10)
        self.ratio = int(self.redisClient.getKey("{}_account_assets_ratio_{}".format(self.token, self.direction)))

        # 亏损(容忍比例)
        if not self.redisClient.getKey("{}_account_assets_loss_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_loss_{}".format(self.token, self.direction), 0.05)
        self.loss = float(self.redisClient.getKey("{}_account_assets_loss_{}".format(self.token, self.direction)))

        # 当出现亏损到达 _account_assets_loss_ 值时, 进行加仓
        # 加仓价格是 min_qty * _account_assets_single_coin_loss_plus_position_multiple_
        # 亏损加仓倍数
        if not self.redisClient.getKey("{}_account_assets_single_coin_loss_plus_position_multiple_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_single_coin_loss_plus_position_multiple_{}".format(self.token, self.direction), 0.25)

        # 默认为 3, 当设置的值大于 1 时一定要根据自身账户总价进行合理的配置
        # 如 _account_assets_single_coin_loss_plus_position_multiple_ 应为越小越好小于或等于 0.25
        # 单币加仓次数
        if not self.redisClient.getKey("{}_account_assets_single_coin_loss_covered_positions_limit_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_single_coin_loss_covered_positions_limit_{}".format(self.token, self.direction), 3)

        # 单币加仓次数计数
        if not self.redisClient.getKey("{}_account_assets_single_coin_loss_covered_positions_count_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_single_coin_loss_covered_positions_count_{}".format(self.token, self.direction), 0)

        # 是否打开单币亏损加仓
        if not self.redisClient.getKey("{}_account_assets_open_single_coin_loss_addition_mode_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_open_single_coin_loss_addition_mode_{}".format(self.token, self.direction), 1)

        # 是否打开盈利方向
        # 1 打开、0 关闭
        if not self.redisClient.getKey("{}_open_profit_order_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_open_profit_order_direction_{}".format(self.token, self.direction), 1)

        # 盈利方向，反向开仓
        ## example: ETH/BUY/LONG
        ## 用于盈利平仓后反向开仓使用
        if not self.redisClient.getKey("{}_profit_order_direction_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_profit_order_direction_{}".format(self.token, self.direction), '')

        # 是否打开双币亏损加仓
        if not self.redisClient.getKey("{}_account_assets_open_double_coin_loss_addition_mode_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_open_double_coin_loss_addition_mode_{}".format(self.token, self.direction), 1)

        # 默认为 1, 当设置的值大于 1 时一定要根据自身账户总价进行合理的配置
        # 加仓的数量为一次 min_qty 的数量
        # 双币币加仓次数
        if not self.redisClient.getKey("{}_account_assets_double_coin_loss_covered_positions_limit_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_double_coin_loss_covered_positions_limit_{}".format(self.token, self.direction), 1)

        # 双币加仓次数计数
        if not self.redisClient.getKey("{}_account_assets_double_coin_loss_covered_positions_count_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_account_assets_double_coin_loss_covered_positions_count_{}".format(self.token, self.direction), 0)

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
        
        26、记录是否开启单币持仓模式 (ETH/BTC): {0}_open_single_coin_contract_trading_pair_{1}
        
        27、最小开仓购买币的数量 Example: 200/USDT: {0}_account_assets_min_qty_{1}
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
        
        # 当出现亏损到达 _account_assets_loss_ 值时, 进行加仓
        # 默认值 0.25 倍, 也就是 25%
        # 加仓价格是 min_qty * _account_assets_single_coin_loss_plus_position_multiple_
        35、亏损加仓倍数: {0}_account_assets_single_coin_loss_plus_position_multiple_{1}
        # 默认为 0.25, 当设置的值大于 1 时一定要根据自身账户总价进行合理的配置
        # 如 _account_assets_single_coin_loss_plus_position_multiple_ 应为越小越好小于或等于 0.25
        36、允许加仓次数: {0}_account_assets_single_coin_loss_covered_positions_limit_{1}
        # 默认 3
        36、加仓次数计数: {0}_account_assets_single_coin_loss_covered_positions_count_{1}
        # 是否打开亏损加仓模式默认 1, 其他任意值为关闭
        38、是否开启加仓: {0}_account_assets_open_single_coin_loss_addition_mode_{1}
        
        # 盈利反向开仓
        ## 默认 1 打开，0 关闭
        39、是否打开盈利反向模式: {0}_open_profit_order_direction_{1}
        ## example: ETHUSDT/BUY/LONG
        40、用于盈利平仓后反向开仓使用: {0}_profit_order_direction_{1}

        41、是否打开双币亏损加仓: {0}_account_assets_open_double_coin_loss_addition_mode_{1}
        42、双币加仓次数: {0}_account_assets_double_coin_loss_covered_positions_limit_{1}
        43、双币加仓累计次数: {0}_account_assets_double_coin_loss_covered_positions_count_{1}

        @@@@@@@@@@@@@@@@@@@@ 账户持仓算法 @@@@@@@@@@@@@@@@@@@@@@@
        单币下单数量 = {0}_account_assets_total_percentage_qty_{1}
        单币亏损加仓数量 = 单币下单数量(20%) * {0}_account_assets_single_coin_loss_plus_position_multiple_{1}
        单币亏损加仓次数 = {0}_account_assets_single_coin_loss_covered_positions_limit_{1}
        双币下单数量 = 单币加单数量 * 1
        双币亏损加仓数量 = 单币下单数量(20%)
        双币亏损加仓次数: {0}_account_assets_double_coin_loss_covered_positions_limit_{1}

        总仓位(90%) = 单币下单数量(20%) + (单币亏损加仓数量 * 单币亏损加仓次数)(15%) + (双币下单数量(20%) + (单币亏损加仓数量 * 单币亏损加仓次数))(15%) + (双币亏损加仓数量 * 双币亏损加仓次数)(20%)
        @@@@@@@@@@@@@@@@@@@@@@@ END @@@@@@@@@@@@@@@@@@@@@@@
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
            # 判断远程 API 当前 orderID 的状态 FILLED 为已经成功建仓 NEW 为委托单 EXPIRED 过期 CANCELED 取消订单
            if orderInfo["status"] == "FILLED":
                logger.info("检查订单 {} 状态正常".format(orderId))
                return False
            logger.warning("当前订单状态: {}".format(orderInfo))
            return True
        except Exception as err:
            logger.error("无法正常获取订单执行方法报错 {}, 对象数据: {}".format(err, orderId))
            return True

    def initializeOrderPriceOld(self, trade, asset='USDT', ratio=1):
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

        @return 可购买 BTC币 真实数量
        """
        return 10000
        # 获取账户可建仓百分比
        # 当此值为 0 使用 _account_assets_min_qty_ 参数为默认委托价格
        self.account_assets_total_percentage_qty = int(self.redisClient.getKey("{}_account_assets_total_percentage_qty_{}".format(self.token, self.direction)))
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
                            return float("{:.3f}".format(qty_number * ratio))
                        else:
                            logger.error("初始化委托价格不能满足使用百分比总仓位, 因超出可用资产金额! 委托价格({}) > 可用资产({})".format(float(qty_number_assets), float(available_assets)))
                            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
        except:
            return float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))

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

        @return 可用 USDT 数量
        """
        # 获取账户可建仓百分比
        # 当此值为小于 3 时, 使用 account_assets_min_qty 参数为默认委托价格
        self.account_assets_total_percentage_qty = int(self.redisClient.getKey("{}_account_assets_total_percentage_qty_{}".format(self.token, self.direction)))
        account_assets_min_qty = float(self.redisClient.getKey("{}_account_assets_min_qty_{}".format(self.token, self.direction)))
        try:
            # 判断此值大于 3 否则小于 3% 仓位开仓没有意义
            if self.account_assets_total_percentage_qty < 3:
                logger.info("当前使用百分比资产值 {} 小于 3, 使用 {} 作为下单价格!".format(self.account_assets_total_percentage_qty, account_assets_min_qty))
                return account_assets_min_qty
            # 判断值大于 3 且小于 100
            elif self.account_assets_total_percentage_qty >= 3 and self.account_assets_total_percentage_qty < 100:
                # 获取账户资产
                account_assets_list = trade.get_balance().json()
                for item in account_assets_list:
                    # 判断并获取 asset 币对资产
                    if item["asset"] == asset:
                        # 获取应建仓位百分比资产
                        account_assets = Decimal(item["balance"]) * Decimal(self.account_assets_total_percentage_qty / 100)
                        # 判断是否大于 可用资产
                        available_assets = Decimal(item['availableBalance'])
                        if account_assets < available_assets:
                            logger.info("计算仓位百分比账户资金为: {}, 倍数: {}".format(account_assets, ratio))
                            return float("{:.3f}".format(account_assets * ratio))
                        else:
                            logger.error("初始化委托价格不能满足使用百分比总仓位, 因超出可用资产金额! 委托价格({}) > 可用资产({})".format(float(account_assets), float(available_assets)))
                            return account_assets_min_qty
            return account_assets_min_qty
        except:
            return account_assets_min_qty

    def symbolStatisticalIncome(self, symbol):
        """
        计算收益
        """
        _symbol_suffix = symbol.replace("USDT", "").lower()
        ## 当前价格
        usdt_present_price = float(self.redisClient.getKey("{}_futures_{}@usdt_present_price_{}".format(self.token, _symbol_suffix, self.direction)))
        ## 最后下单价格
        usdt_last_trade_price = float(self.redisClient.getKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction)))
        ## 获取方向
        LONG_SHORT = self.redisClient.getKey("{}_{}_order_direction_{}".format(self.token, _symbol_suffix, self.direction)).split("|")[1]

        # 判定如果大于 profit 则进行清仓
        if LONG_SHORT == 'SHORT':
            ## 盈亏百分比
            usdt_profi_loss = (usdt_present_price - usdt_last_trade_price) / usdt_present_price * self.ratio * 100
        else:
            ## 盈亏百分比
            usdt_profi_loss = (usdt_last_trade_price - usdt_present_price) / usdt_present_price * self.ratio * 100
        return usdt_profi_loss

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

    def symbolForcedLiquidation(self, trade, symbol):
        """
        清仓
        """
        _symbol_suffix = symbol.replace("USDT", "").lower()
        try:
            ## 获取方向
            BUY_SELL = self.TrendShift(self.redisClient.getKey("{}_{}_order_direction_{}".format(self.token, _symbol_suffix, self.direction)).split("|")[0])
            LONG_SHORT = self.redisClient.getKey("{}_{}_order_direction_{}".format(self.token, _symbol_suffix, self.direction)).split("|")[1]
            ## 获取当前下单池
            order_pool = float(sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_{}@usdt_order_pool_{}".format(self.token, _symbol_suffix, self.direction)))]))
            ## 清仓
            logger.info("{} 开始清仓, 方向: {}/{}, 清仓数量: {}".format(symbol, BUY_SELL, LONG_SHORT, order_pool))
            resOrder = trade.open_order(symbol, BUY_SELL, order_pool, price=None, positionSide=LONG_SHORT).json()
            if not 'orderId' in resOrder.keys():
                logger.error('{} 清仓失败, 错误提示: {}, 触发时间: {}'.format(symbol, str(resOrder), PublicModels.changeTime(time.time())))
                return False
            else:
                # 记录订单
                order_number_pool = json.loads(self.redisClient.getKey("{}_futures_{}@usdt_sell_order_number_pool_{}".format(self.token, _symbol_suffix, self.direction)))
                order_number_pool.append(resOrder["orderId"])
                # 检查订单是否完成, 否则阻塞
                while self.checkOrder(trade, symbol, resOrder["orderId"]):
                    time.sleep(1)
                    logger.warning('{} 清仓订单状态异常订单号 {} 订单状态 {}, {}/{}'.format(symbol, resOrder["orderId"], resOrder["status"], BUY_SELL, LONG_SHORT))
                self.redisClient.setKey("{}_futures_{}@usdt_sell_order_number_pool_{}".format(self.token, _symbol_suffix, self.direction), json.dumps(order_number_pool))

                # 获取当前 gas
                all_order_gas = float(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
                # 计算当前 ETC USDT 数量
                usdt_number = Decimal(order_pool) * Decimal(float(self.redisClient.getKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction))))
                # 计算 gas 费用
                now_gas = (usdt_number * Decimal(0.0004)) + Decimal(all_order_gas)
                self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))

                # 清除下单价格
                self.redisClient.setKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction), 0.0)
                # 清除下单池
                self.redisClient.setKey("{}_futures_{}@usdt_order_pool_{}".format(self.token, _symbol_suffix, self.direction), '[]')
                # 清除下单方向
                self.redisClient.setKey("{}_{}_order_direction_{}".format(self.token, _symbol_suffix, self.direction), '')
                # 初始化单币模式
                self.initOpenSingleCurrencyContractTradingPair(symbol='ETH')
                # 开启下单模式
                self.redisClient.setKey("{}_futures_{}@usdt_order_pause_{}".format(self.token, _symbol_suffix, self.direction), 0)

                logger.info('{} 清仓成功, 卖出数量: {}, 等价 USDT: {:.2f}, GAS: {:.2f}'.format(symbol, order_pool, float(usdt_number), float(now_gas)))
                return resOrder
        except Exception as err:
            logger.error('{} 清仓异常错误: {}'.format(symbol, err))
            return False
        
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
        # 是否开启盈利反方向开仓模式
        open_profit_order_direction = int(self.redisClient.getKey("{}_open_profit_order_direction_{}".format(self.token, self.direction)))
        profit_order_direction = self.redisClient.getKey("{}_profit_order_direction_{}".format(self.token, self.direction))
        if (open_profit_order_direction == 1) and profit_order_direction:
            # 重置盈利方向
            self.redisClient.setKey("{}_profit_order_direction_{}".format(self.token, self.direction), '')
            return self.TrendShift(profit_order_direction.split("|")[1]), profit_order_direction.split("|")[2]

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

    def CreateNewOrder(self, symbol, trade, BUY_SELL, LONG_SHORT, quantity, price=None):
        """
        创建订单
        trade 操作账户
        BUY_SELL 多/空
        LONG_SHORT 买/卖
        quantity 订单数量
        price 如果为 None 为市价, 如果是 float 则限价

        @return False/True
        """
        _symbol_suffix = symbol.replace("USDT", "").lower()
        resOrder = trade.open_order('{}'.format(symbol), BUY_SELL, quantity, price=price, positionSide=LONG_SHORT).json()
        if not 'orderId' in resOrder.keys():
            if resOrder['msg'] == 'Margin is insufficient.':
                logger.error('{} 建仓失败, 可用金不足, 错误提示: {}, 触发时间: {}, 下单方向: {}/{}, 下单金额: {}'.format(symbol, str(resOrder), PublicModels.changeTime(time.time()), BUY_SELL, LONG_SHORT, quantity))
            else:
                logger.error('{} 建仓失败, 错误信息: {}, 触发时间: {}, 下单方向: {}/{}, 下单金额: {}'.format(symbol, str(resOrder), PublicModels.changeTime(time.time()), BUY_SELL, LONG_SHORT, quantity))
            return False
        else:
            # 记录订单
            coin_buy_order_number_pool = json.loads(self.redisClient.getKey("{}_futures_{}@usdt_buy_order_number_pool_{}".format(self.token, _symbol_suffix, self.direction)))
            coin_buy_order_number_pool.append(resOrder["orderId"])
            self.redisClient.setKey("{}_futures_{}@usdt_buy_order_number_pool_{}".format(self.token, _symbol_suffix, self.direction), json.dumps(usdt_buy_order_number_pool))
            # 记录下单价格
            coin_last_trade_price = Decimal(self.redisClient.getKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction)))
            if coin_last_trade_price == 0:
                self.redisClient.setKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction), self.redisClient.getKey("{}_futures_{}@usdt_present_price_{}".format(self.token, _symbol_suffix, self.direction)))
            else:
                # 获取下单池
                coin_order_pool = sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_{}@usdt_order_pool_{}".format(self.token, _symbol_suffix, self.direction)))])
                coin_last_trade_price = Decimal(self.redisClient.getKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction)))
                coin_present_price = Decimal(self.redisClient.getKey("{}_futures_{}@usdt_present_price_{}".format(self.token, _symbol_suffix, self.direction)))
                # 计算均价
                coin_order_svg = ((coin_last_trade_price * coin_order_pool) + (coin_present_price * Decimal(quantity))) / (coin_order_pool + Decimal(quantity))
                self.redisClient.setKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction), "{:.5f}".format(float(coin_order_svg)))
            # 记录下单池
            coin_order_pool = json.loads(self.redisClient.getKey("{}_futures_{}@usdt_order_pool_{}".format(self.token, _symbol_suffix, self.direction)))
            coin_order_pool.append(quantity)
            self.redisClient.setKey("{}_futures_{}@usdt_order_pool_{}".format(self.token, _symbol_suffix, self.direction), json.dumps(coin_order_pool))
            # 记录下单方向
            self.redisClient.setKey("{}_{}_order_direction_{}".format(self.token, _symbol_suffix, self.direction), "{}|{}".format(BUY_SELL, LONG_SHORT))
            # 获取当前 gas
            all_order_gas = Decimal(self.redisClient.getKey("{}_all_order_gas_{}".format(self.token, self.direction)))
            # 计算当前 USDT 数量
            usdt_number = Decimal(quantity) * Decimal(self.redisClient.getKey("{}_futures_{}@usdt_last_trade_price_{}".format(self.token, _symbol_suffix, self.direction)))
            # 计算 gas 费用
            now_gas = (usdt_number * Decimal(0.0004)) + all_order_gas
            self.redisClient.setKey("{}_all_order_gas_{}".format(self.token, self.direction), float(now_gas))
            # 记录下单时间
            self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())

            logger.info('{} 建仓成功, 购买数量: {}, 订单返回值: {}, 订单方向: {}/{}, 等价 USDT: {}, GAS: {}'.format(symbol, quantity, resOrder, BUY_SELL, LONG_SHORT, usdt_number, now_gas))
        return resOrder

    def initOpenSingleCurrencyContractTradingPair(self, symbol='ETH'):
        """
        初始化单币模式
        """
        self.redisClient.setKey("{}_open_single_coin_contract_trading_pair_{}".format(self.token, self.direction), symbol)

    def usdtConvertsCoins(self, symbol='BTC', quantity=0.0):
        """
        USDT 转换 比对可购买数量
        """
        try:
            futures_usdt_present_price = self.redisClient.getKey("{}_futures_{}@usdt_present_price_{}".format(self.token, symbol.lower(), self.direction))
            # usdt 转换 币 真实数量，并做四舍五入
            qty_number = round(Decimal(quantity) / Decimal(futures_usdt_present_price), 3)
            # 需大于最小下单价格: 0.001
            if qty_number < Decimal('0.001'):
                logger.info("{0} -> USDT 转换阶段, 可使用 {1}(USDT) 转换 {2}({0})".format(symbol, quantity, 0.001))
                return 0.001
            else:
                logger.info("{0} -> USDT 转换阶段, 可使用 {1}(USDT) 转换 {2}({0})".format(symbol, quantity, qty_number))
                return float(qty_number)
        except BaseException as err:
            logger.error("{0} -> USDT 异常转换阶段, 可使用 {1}(USDT) 转换 {2}({0}), 错误提示: {3}".format(symbol, quantity, 0.0, err))
            return 0.0

    def DoubleCoinPlusWarehouse(self, btc_usdt_profit_loss, eth_usdt_profit_loss, trade):
        """
        判定亏损达到一定阀值后进行双币加仓
        """
        # 获取最新委托价格值
        self.min_qty = self.initializeOrderPrice(trade=trade, asset='USDT', ratio=self.ratio)
        # 计算 ETH 购买数量
        ethUsdtOrderQuantity = self.usdtConvertsCoins(symbol='ETH', quantity=self.min_qty)

        # 是否打开双币亏损加仓模式
        account_assets_open_double_coin_loss_addition_mode = int(self.redisClient.getKey("{}_account_assets_open_double_coin_loss_addition_mode_{}".format(self.token, self.direction)))
        account_assets_double_coin_loss_covered_positions_limit = int(self.redisClient.getKey("{}_account_assets_double_coin_loss_covered_positions_limit_{}".format(self.token, self.direction)))
        account_assets_double_coin_loss_covered_positions_count = int(self.redisClient.getKey("{}_account_assets_double_coin_loss_covered_positions_count_{}".format(self.token, self.direction)))
        if account_assets_open_double_coin_loss_addition_mode != 1:
            return
        # 判断是否达到加仓上线
        if account_assets_double_coin_loss_covered_positions_count >= account_assets_double_coin_loss_covered_positions_limit:
            logger.info("已达到双币亏损后加仓上限!")
            return
        # 判定两个收益率都是小于 -1, 且 eth 亏损的3倍大于 btc 的亏损时, 对 eth 进行加仓
        if (-1 > btc_usdt_profit_loss) and (-1 > eth_usdt_profit_loss) and ((eth_usdt_profit_loss * 3) > btc_usdt_profit_loss):
            logger.info("ETHUSDT 进行亏损补仓数量: {}".format(ethUsdtOrderQuantity))

            ## 获取 ETH 方向
            BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
            LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]

            ## 设置补仓数量
            self.redisClient.setKey("{}_account_assets_double_coin_loss_covered_positions_count_{}".format(self.token, self.direction), (account_assets_double_coin_loss_covered_positions_count + 1))
            ## 建仓
            if not self.CreateNewOrder('ETHUSDT', trade, BUY_SELL, LONG_SHORT, ethUsdtOrderQuantity):
                return

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
            self.open_single_currency_contract_trading_pair = self.redisClient.getKey("{}_open_single_coin_contract_trading_pair_{}".format(self.token, self.direction))

            # 判断当前是否开启单币仓位模式
            if self.open_single_currency_contract_trading_pair != 'NULL':
                try:
                    time.sleep(0.3)
                    # 强制平仓
                    if self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)) == 'true':
                        logger.info('{} 强制平仓'.format('ETHUSDT'))

                        ## ETH/USDT 清仓
                        g2 = Process(target=self.symbolForcedLiquidation, args=(trade, 'ETHUSDT',))
                        g2.start()

                        # 设置暂停建仓
                        self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)

                        # 恢复强制平仓配置
                        self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')

                        # 计算收益
                        eth_usdt_profi_loss = self.symbolStatisticalIncome('ETHUSDT')
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
                        self.initOpenSingleCurrencyContractTradingPair(symbol='NULL')
                        continue

                    # 如果没有被下单则进行第一次下单
                    elif len(btc_usdt_order_pool) == 0 and len(eth_usdt_order_pool) == 0:
                        time.sleep(5)
                        # 单币初始化加仓配置
                        self.redisClient.setKey("{}_account_assets_single_coin_loss_covered_positions_count_{}".format(self.token, self.direction), 0)
                        # 双币初始化加仓配置
                        self.redisClient.setKey("{}_account_assets_double_coin_loss_covered_positions_count_{}".format(self.token, self.direction), 0)

                        # 停止下单
                        if self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)) == 'true':
                            logger.info('{} 停止下单状态'.format('BTCUSDT and ETHUSDT'))
                            time.sleep(5)
                            continue
                        # 获取最新委托价格值
                        self.min_qty = self.initializeOrderPrice(trade=trade, asset='USDT', ratio=self.ratio)

                        ethUsdtOrderQuantity = self.usdtConvertsCoins(symbol='ETH', quantity=self.min_qty)

                        ## 获取 ETH 方向
                        BUY_SELL, LONG_SHORT = self.LongShortDirection('ETHUSDT')

                        logger.info('{} 准备建仓单币'.format('ETHUSDT'))
                        if not self.CreateNewOrder('ETHUSDT', trade, BUY_SELL, LONG_SHORT, ethUsdtOrderQuantity):
                            continue
                    else:
                        # 如果非第一次下单则进入此规则
                        ## 获取 ETH 方向
                        ETH_BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
                        ETH_LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]

                        # 计算收益
                        eth_usdt_profi_loss = self.symbolStatisticalIncome('ETHUSDT')
                        logger.info('ETHUSDT 方向: {}/{}, 最新价格: {}, 系数: {}'.format(ETH_BUY_SELL, ETH_LONG_SHORT, float(self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction))), float(self.redisClient.getKey("{}_spot_eth@btc_present_price_{}".format(self.token, self.direction)))))

                        # 判断收益
                        if (eth_usdt_profi_loss) >= (self.profit * 3):
                            logger.info('准备清仓单币, 当前 ETHUSDT 盈损比例 {}%, 杠杆倍数: {}, 合计 {}%'.format(eth_usdt_profi_loss, self.ratio, eth_usdt_profi_loss))
                            ## 设置盈利方向
                            self.redisClient.setKey("{}_profit_order_direction_{}".format(self.token, self.direction), '{}|{}|{}'.format('ETHUSDT', ETH_BUY_SELL, ETH_LONG_SHORT))

                            ## ETH/USDT 清仓
                            g2 = Process(target=self.symbolForcedLiquidation, args=(trade, 'ETHUSDT',))
                            g2.start()

                            # 初始化暂停建仓
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

                            # 判断是否打开亏损加仓
                            open_loss_addition_mode = int(self.redisClient.getKey("{}_account_assets_open_single_coin_loss_addition_mode_{}".format(self.token, self.direction)))
                            # 获取亏损配置初始数据
                            loss_covered_positions_limit = int(self.redisClient.getKey("{}_account_assets_single_coin_loss_covered_positions_limit_{}".format(self.token, self.direction)))
                            loss_covered_positions_count = int(self.redisClient.getKey("{}_account_assets_single_coin_loss_covered_positions_count_{}".format(self.token, self.direction)))
                            loss_plus_position_multiple = float(self.redisClient.getKey("{}_account_assets_single_coin_loss_plus_position_multiple_{}".format(self.token, self.direction)))

                            if open_loss_addition_mode == 1:
                                logger.info("进入单币亏损加仓初始阶段..")
                                # 判断当前加仓的次数
                                if loss_covered_positions_limit <= loss_covered_positions_count:
                                    logger.warning("加仓触发限制, 无法进行加仓! 进入双币开仓初始阶段!, 当前次数: {}, 上限次数: {}".format(loss_covered_positions_count, loss_covered_positions_limit))
                                    # 计算加仓的委托数量
                                    self.min_qty = self.min_qty + ((self.min_qty * loss_plus_position_multiple) * loss_covered_positions_count)
                                elif loss_covered_positions_limit > loss_covered_positions_count:
                                    loss_covered_positions_count = loss_covered_positions_count + 1
                                    logger.info("{} 进行单币亏损加仓计算阶段, 当前次数: {}, 上限次数: {}, 开仓数量: ({}(委托价) * {}(加仓比例))".format('ETHUSDT', loss_covered_positions_count, loss_covered_positions_limit, self.min_qty, loss_plus_position_multiple))
                                    ## 计算 ETH 下单数量
                                    _ethUsdtOrderQuantity = self.usdtConvertsCoins(symbol='ETH', quantity=self.min_qty)
                                    ethUsdtOrderQuantity = float('{:.3f}'.format(Decimal(_ethUsdtOrderQuantity * loss_plus_position_multiple)))

                                    ## 获取 ETH 方向
                                    BUY_SELL = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[0]
                                    LONG_SHORT = self.redisClient.getKey("{}_eth_order_direction_{}".format(self.token, self.direction)).split("|")[1]

                                    # 对当前数量加一
                                    self.redisClient.setKey("{}_account_assets_single_coin_loss_covered_positions_count_{}".format(self.token, self.direction), loss_covered_positions_count)

                                    logger.info('{} 准备单币亏损加仓, 方向: {}/{}, 委托数量: {}'.format('ETHUSDT', BUY_SELL, LONG_SHORT, ethUsdtOrderQuantity))
                                    if not self.CreateNewOrder('ETHUSDT', trade, BUY_SELL, LONG_SHORT, ethUsdtOrderQuantity):
                                        continue

                                    logger.info('{} 单币亏损加仓成功!..'.format('ETHUSDT'))
                                    time.sleep(5)
                                    continue

                            ## 获取 BTC 方向
                            BUY_SELL = 'SELL' if ETH_BUY_SELL == 'BUY' else 'BUY'
                            LONG_SHORT = 'SHORT' if ETH_LONG_SHORT == 'LONG' else 'LONG'

                            btcUsdtOrderQuantity = self.usdtConvertsCoins(symbol="BTC", quantity=self.min_qty)

                            ## BTC/USDT 开单(最小下单量 0.001)
                            logger.info('{} 准备建仓, 进入单币转双币, 方向: {}/{}, 委托数量: {}'.format('BTCUSDT', BUY_SELL, LONG_SHORT, btcUsdtOrderQuantity))
                            if not self.CreateNewOrder('BTCUSDT', trade, BUY_SELL, LONG_SHORT, btcUsdtOrderQuantity):
                                continue
                            # 关闭单币模式
                            self.initOpenSingleCurrencyContractTradingPair(symbol='NULL')
                            logger.info('{} 单币转双币加仓成功!..'.format('BTCUSDT'))
                        else:
                            order_coin_number_pool = sum([Decimal(item) for item in json.loads(self.redisClient.getKey("{}_futures_{}@usdt_order_pool_{}".format(self.token, 'eth', self.direction)))])
                            logger.info('持续监听单币模式, ETHUSDT 盈损比例 {:.2f}%, 杠杆倍数: {}, 下单价格: {:.2f}, 下单数量: {:.2f}'.format(eth_usdt_profi_loss, self.ratio, float(self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction))), order_coin_number_pool))

                except Exception as err:
                    logger.error('{} 单币主逻辑异常错误: {}'.format('ETHBTC', err))
            else:
                try:
                    time.sleep(0.3)
                    # 强制平仓
                    if self.redisClient.getKey("{}_forced_liquidation_{}".format(self.token, self.direction)) == 'true':
                        logger.info('{} 强制平仓'.format('BTCUSDT'))

                        ## BTC/USDT 清仓
                        g1 = Process(target=self.symbolForcedLiquidation, args=(trade, 'BTCUSDT',))
                        ## ETH/USDT 清仓
                        g2 = Process(target=self.symbolForcedLiquidation, args=(trade, 'ETHUSDT',))

                        g1.start()
                        g2.start()

                        # 设置暂停建仓
                        self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)
                        self.redisClient.setKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction), 1)

                        # 恢复强制平仓配置
                        self.redisClient.setKey("{}_forced_liquidation_{}".format(self.token, self.direction), 'false')

                        # 计算收益
                        btc_usdt_profi_loss, eth_usdt_profi_loss = self.symbolStatisticalIncome('BTCUSDT'), self.symbolStatisticalIncome('ETHUSDT')
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

                        # 停止下单
                        if self.redisClient.getKey("{}_order_pause_{}".format(self.token, self.direction)) == 'true':
                            logger.info('{} 停止下单状态'.format('BTCUSDT and ETHUSDT'))
                            time.sleep(5)
                            continue
                        else:
                            # 获取最新委托价格值
                            self.min_qty = self.initializeOrderPrice(trade=trade, asset='USDT', ratio=self.ratio)

                            ## 获取 BTC 方向
                            BUY_SELL, LONG_SHORT = self.LongShortDirection('BTCUSDT')

                            # 计算 BTC 购买数量
                            btcUsdtOrderQuantity = self.usdtConvertsCoins(symbol="BTC", quantity=self.min_qty)

                            ## BTC/USDT 开单(最小下单量 0.001)
                            logger.info('{} 准备建仓双币, 下单方向: {}/{}, 下单数量: {}'.format('BTCUSDT', BUY_SELL, LONG_SHORT, btcUsdtOrderQuantity))

                            if not self.CreateNewOrder('BTCUSDT', trade, BUY_SELL, LONG_SHORT, btcUsdtOrderQuantity):
                                continue

                            # 计算 ETH 购买数量
                            ethUsdtOrderQuantity = self.usdtConvertsCoins(symbol='ETH', quantity=self.min_qty)

                            ## 获取方向
                            BUY_SELL = 'SELL' if BUY_SELL == 'BUY' else 'BUY'
                            LONG_SHORT = 'SHORT' if LONG_SHORT == 'LONG' else 'LONG'

                            logger.info('{} 准备建仓双币, 下单方向: {}/{}, 下单数量: {}'.format('ETCUSDT', BUY_SELL, LONG_SHORT, ethUsdtOrderQuantity))

                            if not self.CreateNewOrder('ETHUSDT', trade, BUY_SELL, LONG_SHORT, ethUsdtOrderQuantity):
                                continue

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
                        btc_usdt_profit_loss, eth_usdt_profit_loss = self.symbolStatisticalIncome('BTCUSDT'), self.symbolStatisticalIncome('ETHUSDT')
                        logger.info('当前 BTCUSDT 方向: {}/{} 最新价格: {}, ETHUSDT 方向: {}/{} 最新价格: {}'.format(BTC_BUY_SELL, BTC_LONG_SHORT, self.redisClient.getKey("{}_futures_btc@usdt_present_price_{}".format(self.token, self.direction)), ETH_BUY_SELL, ETH_LONG_SHORT, self.redisClient.getKey("{}_futures_eth@usdt_present_price_{}".format(self.token, self.direction))))

                        if (btc_usdt_profit_loss + eth_usdt_profit_loss) >= self.profit:
                            logger.info('准备清仓双币, 当前 BTCUSDT 盈损比例 {:.2f}%, ETHUSDT 盈损比例 {:.2f}%, 合计 {:.2f}%'.format(btc_usdt_profit_loss, eth_usdt_profit_loss, btc_usdt_profit_loss + eth_usdt_profit_loss))
                            ## 设置盈利方向
                            if btc_usdt_profit_loss > eth_usdt_profit_loss:
                                self.redisClient.setKey("{}_profit_order_direction_{}".format(self.token, self.direction), '{}|{}|{}'.format('BTCUSDT', BTC_BUY_SELL, BTC_LONG_SHORT))
                            else:
                                self.redisClient.setKey("{}_profit_order_direction_{}".format(self.token, self.direction), '{}|{}|{}'.format('ETHUSDT', ETH_BUY_SELL, ETH_LONG_SHORT))

                            ## BTC/USDT 清仓
                            g1 = Process(target=self.symbolForcedLiquidation, args=(trade, 'BTCUSDT',))
                            ## ETH/USDT 清仓
                            g2 = Process(target=self.symbolForcedLiquidation, args=(trade, 'ETHUSDT',))

                            g1.start()
                            g2.start()

                            # 设置暂停建仓
                            self.redisClient.setKey("{}_futures_eth@usdt_order_pause_{}".format(self.token, self.direction), 1)
                            self.redisClient.setKey("{}_futures_btc@usdt_order_pause_{}".format(self.token, self.direction), 1)

                            # 计算收益
                            all_order_profit = Decimal(self.redisClient.getKey("{}_all_order_profit_{}".format(self.token, self.direction)))
                            now_profit = Decimal(btc_usdt_profit_loss + eth_usdt_profit_loss) + all_order_profit
                            self.redisClient.setKey("{}_all_order_profit_{}".format(self.token, self.direction), float(now_profit))

                        else:
                            # 双币亏损加仓
                            self.DoubleCoinPlusWarehouse(btc_usdt_profit_loss, eth_usdt_profit_loss, trade)
                            logger.info('持续监听双币模式, 当前 BTCUSDT 仓位价格: {} 盈损比例 {:.2f}%, ETHUSDT 仓位价格: {:.2f} 盈损比例 {:.2f}%, 杠杆倍数: {}, 合计 {:.2f}%'.format(self.redisClient.getKey("{}_futures_btc@usdt_last_trade_price_{}".format(self.token, self.direction)), btc_usdt_profit_loss, self.redisClient.getKey("{}_futures_eth@usdt_last_trade_price_{}".format(self.token, self.direction)), eth_usdt_profit_loss, self.ratio, (btc_usdt_profit_loss + eth_usdt_profit_loss)))
                except Exception as err:
                    logger.error('{} 双币主逻辑异常错误: {}'.format('ETHBTC', err))

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'key': args.key, 'secret': args.secret, 'token': args.token, 'redis_host': args.rhost, 'redis_port': args.rport, 'redis_db': args.rdb, 'redis_auth': args.rauth}
    
    gs = GridStrategy(**conn_setting)
    gs.run()
    gs.join()
