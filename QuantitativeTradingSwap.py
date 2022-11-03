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
        self.direction = "LONG" if self.side == "多" else "SHORT"

        # 初始化 Redis 默认数据
        # symbol
        if not self.redisClient.getKey("{}_symbol_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_symbol_{}".format(self.token, self.direction), self.symbol)
        elif self.redisClient.getKey("{}_symbol_{}".format(self.token, self.direction)) != self.symbol:
            raise AssertionError("当前运行 Symbol {} 与上一次运行 Symbol {} 不相符! 请更换 Token 以便区分数据冲突.".format(self.symbol, self.redisClient.getKey("{}_symbol_{}".format(self.token, self.direction))))

        # win default
        # 记录止损值(值是购买U的数量)
        if not self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), 0.0)
        # avg default
        # 记录均价
        if not self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
        # last_trade_price default
        # 下单时的价格
        if not self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
        # lowest_price default
        # 记录最低价用于加仓参考
        if not self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
        # highest_price default
        # 记录最高价
        if not self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
        # base_price default
        # 记录正加仓
        if not self.redisClient.getKey("{}_base_price_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
        # avg_tmp default
        # 延迟记录均价变化(开单均价)
        if not self.redisClient.getKey("{}_avg_tmp_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)
        # max_position default
        # 记录实盘最大仓位, 供后续参考
        if not self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction)):
            self.redisClient.setKey("{}_max_position_{}".format(self.token, self.direction), 0)
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
                klines = get_history_k(typ='futures', coin=self.symbol, T='1m', limit=500).json()
                # 获取 k 线中最低的价格(取每个 list 中第 3 个位置数据)
                price1m_low = list(map(lambda x: float(x[3]), klines))
                # 获取 k 线中最高的价格(取每个 list 中第 2 个位置数据)
                price1m_high = list(map(lambda x: float(x[2]), klines))
                # 记录最小购买单价
                self.redisClient.setKey("{}_position_size_{}".format(self.token, self.direction), self.min_qty)
                try:
                    # 获取 k 线中现在的价格(第一个价格)
                    self.redisClient.setKey("{}_present_price_{}".format(self.token, self.direction), float(klines[-1][4]))
                except:
                    # 获取最新价格
                    # 有请求延迟
                    self.redisClient.setKey("{}_present_price_{}".format(self.token, self.direction), float(get_present_price('{}'.format(self.symbol)).json()['price']))

                # 如果策略为开 空 时
                if self.side != '多':
                    self.logger.info('{}/{} U本位合约正在运行, 当前价格 {} , 已购买币种总数 {} , 已经下单总次数 {} \t {}'.format(
                        self.symbol, self.side, float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])), len([float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)]), PublicModels.changeTime(time.time())))

                    sell_condition1 = float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= (min(price1m_low[-3:]) + max(price1m_high[-3:])) / 2

                    # 起始位置 0, 且没有开仓
                    if int(self.redisClient.llenKey("{}_short_qty".format(self.token))) == 0:

                        # 判断数据是否为空
                        if sell_condition1:
                            # 判断上一次下单间隔, 如果未到达跳出当前判断
                            if time.time() - float(self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction))) < self.order_interval:
                                continue

                            self.logger.info('{}/{} 下单开空, 下单数量 {}, 下单价格 {} {}'.format(self.symbol, self.side, self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction)), self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)), PublicModels.changeTime(time.time())))

                            # 下单开空, 市价开单
                            res_short = trade.open_order(self.symbol, 'SELL', float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='SHORT').json()

                            # 判断下单是否成功
                            if not 'orderId' in res_short.keys():
                                self.logger.info('{}/{} 下单开空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                continue
                            else:
                                self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                # 记录购买数量到 buy_qty 列表中
                                self.redisClient.lpushKey("{}_short_qty".format(self.token), self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())

                             # 记录开仓价格
                            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))
                            # 记录起始价格
                            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))
                            # 记录出售价格
                            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))
                            # 科学记数法到十进制 https://calculator.name/scientific-notation-to-decimal
                            # 4e-4 等于 4/10000
                            # 记录止损值(值是购买币的数量)
                            _win = (float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))) * float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) * 4e-4) - float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)

                            # 下单成功
                            self.logger.info('%s/%s 当前仓位成本=%.1f, 开仓价=%.3f \t %s' % (
                                self.symbol,
                                self.side,
                                float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                PublicModels.changeTime(time.time())))

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction)
                            self.logger.info(_env)

                    # 当锚点为负数时, 证明已下过单
                    elif int(self.redisClient.llenKey("{}_short_qty".format(self.token))) > 0:
                        # 判断是否可以继续下单，返回布尔值
                        # 开仓总币价 / 每单币价 < 开仓数量
                        condition = float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)])) / self.min_qty < self.max_add_times
                        # 判断 仓位 是否需要进行止损(全仓平仓)
                        ## 判断 亏损 && (是否可以继续开仓) && 当前价格 大于等于 准备出售价格 乘以 (1 + 1.2 * 开仓数量比例值) ep: 19700.0 * (1 + 1.2 * np.log(1 - -1))
                        ## 主要判断亏损如果超过范围则进行止损平仓（开仓数量到达上限）
                        if self.if_loss and (not condition) and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) * (1 - self.add_rate * np.log(1 + int(self.redisClient.llenKey("{}_short_qty".format(self.token))))):
                            self.logger.info('{}/{} 平空止损 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                            if int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))) == 0:
                                self.logger.info('%s/%s 平多止损失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                continue

                            if int(self.redisClient.llenKey("{}_short_qty".format(self.token))) > int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))):
                                res_short = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()

                                if not 'orderId' in res_short.keys():
                                    self.logger.info('%s/%s 平空止损失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    # 因使用 _real_short_qty 作为清仓对象则需要与 _short_qty 进行同步清除数据
                                    _real_short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)]
                                    _short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)]
                                    
                                    for order_price in _real_short_qty:
                                        _check_number = toolsMethod.checkListDetermine(_short_qty, order_price)
                                        if _check_number[0]:
                                            for index, item in enumerate(_check_number[1]):
                                                self.redisClient.lremKey("{}_short_qty".format(token), item, _check_number[2][index])

                                    _win = (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                            else:
                                # 下单平空(市价平所有仓位)
                                res_short = trade.open_order(self.symbol, 'BUY', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='SHORT').json()

                                # 判断下单平空
                                if not 'orderId' in res_short.keys():
                                    self.logger.info('{}/{} 平空止损失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    self.redisClient.delKey("{}_short_qty".format(self.token))
                                    _win = (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))

                            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                            self.logger.info(_env)

                        ## 如果仓位亏损继续扩大则到达比例后进行加仓
                        ## 判断是否可以加仓
                        ## 20598.0 >= 20498.0 * (1 + 0.006 * np.log(1 + 1))
                        elif condition and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) * (1 -
                         self.add_rate * np.log(1 + int(self.redisClient.llenKey("{}_short_qty".format(self.token))))):

                            # 判断上一次下单间隔, 如果未到达跳出当前判断
                            if time.time() - float(self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction))) < self.order_interval:
                                continue

                            if float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))) * (1 - (float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))) / float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) - 1) / 5):
                                self.logger.info('{}/{} 虚亏加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                                # 下单加仓, 加仓会加整个仓位的一倍
                                res_short = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='SHORT').json()

                                # 判断下单加仓
                                if not 'orderId' in res_short.keys():
                                    if res_short['msg'] == 'Margin is insufficient.':
                                        self.logger.info('{}/{} 虚亏加仓失败, 可用金不足 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    else:
                                        self.logger.info('{}/{} 虚亏加仓失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    self.redisClient.lpushKey("{}_short_qty".format(self.token), float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])))
                                    self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())

                                _highest_price = max(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))))
                                self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), _highest_price)

                                _avg = (Decimal(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) + Decimal(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))))) / 2
                                self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), float(_avg))
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))))
                                _win = ([float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)][-1] * float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) * 4e-4) - float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)

                                self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮亏=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t%s' % (
                                    self.symbol, 
                                    self.side, 
                                    float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))), 
                                    float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))), 
                                    float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))), 
                                    float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))), 
                                    float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))), 
                                    (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600, 
                                    PublicModels.changeTime(time.time())))

                                _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                self.logger.info(_env)

                        ## 如果仓位盈利且到达阀值后进行止盈平仓
                        ## 判断 not condition 能继续开仓且 当前最新价格 >= 购买价格 * (1 + 加减仓百分比阀值 * 下单数量的自然对数)
                        ## 第一单盈利大于 0.00566 左右就可以盈利清仓
                        elif (not condition) and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) * (1 + self.add_rate * np.log(1 + int(self.redisClient.llenKey("{}_short_qty".format(self.token))))):
                            self.logger.info('{}/{} 重新开始下一轮 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                            if int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))) == 0:
                                self.logger.info('%s/%s 重新开始下一轮失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                continue

                            if int(self.redisClient.llenKey("{}_short_qty".format(self.token))) > int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))):

                                _sell_number = [Decimal(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)]

                                res_short = trade.open_order(self.symbol, 'SELL', float(sum(_sell_number[-2:])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.min_profit), self.price_precision), positionSide='LONG').json()
                                if not 'orderId' in res_short.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败1 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    # 因使用 _real_short_qty 作为清仓对象则需要与 _short_qty 进行同步清除数据
                                    _real_short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)]
                                    _short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)]

                                    for order_price in _real_short_qty[-2:]:
                                        _check_number = toolsMethod.checkListDetermine(_short_qty, order_price)
                                        if _check_number[0]:
                                            for index, item in enumerate(_check_number[1]):
                                                self.redisClient.lremKey("{}_short_qty".format(token), item, _check_number[2][index])
                                                

                                res_short = trade.open_order(self.symbol, 'SELL', float(sum(_sell_number[:-2])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.min_profit), self.price_precision), positionSide='LONG').json()
                                if not 'orderId' in res_short.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败2 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    # 因使用 _real_short_qty 作为清仓对象则需要与 _short_qty 进行同步清除数据
                                    _real_short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)]
                                    _short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)]

                                    for order_price in _real_short_qty[:-2]:
                                        _check_number = toolsMethod.checkListDetermine(_short_qty, order_price)
                                        if _check_number[0]:
                                            for index, item in enumerate(_check_number[1]):
                                                self.redisClient.lremKey("{}_short_qty".format(token), item, _check_number[2][index])
                            else:
                                _sell_number = [Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)]

                                res_short = trade.open_order(self.symbol, 'BUY', float(sum(_sell_number[-2:])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 - self.min_profit), self.price_precision), positionSide='SHORT').json()
                                if not 'orderId' in res_short.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败1 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    for item in _sell_number[-2:]:
                                        self.redisClient.brpopKey("{}_short_qty".format(self.token))

                                res_short = trade.open_order(self.symbol, 'BUY', float(sum(_sell_number[:-2])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 - self.profit), self.price_precision), positionSide='SHORT').json()
                                if not 'orderId' in res_short.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败2 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                    for item in _sell_number[:-2]:
                                        self.redisClient.blpopKey("{}_short_qty".format(self.token))
                                        
                            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                            self.logger.info(_env)

                        # 判断 第一次开仓后 && (当前价格 小于等于 购买价格 * (1 - self.min_profit)) && 最低价格 < 100000
                        elif int(self.redisClient.llenKey("{}_short_qty".format(self.token))) == 1 and (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 - self.profit) or (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 - self.min_profit) and float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))) < 100000)):

                            # 最高处回调达到止盈位置则减仓一次
                            # 当盈利大于 0.00128 时就可以进行清仓
                            if float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))) * (1 + (1 - float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))) / float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))) / 5):  # 重仓情形考虑回本平一半或平xx%的仓位, 待计算, 剩下依然重仓考虑吃多少点清仓
                                self.logger.info('{}/{} 盈利平空全仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                                if int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))) == 0:
                                    self.logger.info('%s/%s 盈利平空全仓失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                    continue

                                if int(self.redisClient.llenKey("{}_short_qty".format(self.token))) > int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))):

                                    res_short = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                                    if not 'orderId' in res_short.keys():
                                        self.logger.info('%s/%s 盈利平空全仓失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                        continue
                                    else:
                                        self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                        # 因使用 _real_short_qty 作为清仓对象则需要与 _short_qty 进行同步清除数据
                                        _real_short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_short_qty".format(self.token), 0, -1)]
                                        _short_qty = [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)]

                                        for order_price in _real_short_qty:
                                            _check_number = toolsMethod.checkListDetermine(_short_qty, order_price)
                                            if _check_number[0]:
                                                for index, item in enumerate(_check_number[1]):
                                                    self.redisClient.lremKey("{}_short_qty".format(token), item, _check_number[2][index])
                                else:
                                    res_short = trade.open_order(self.symbol, 'BUY', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='SHORT').json()
                                    if not 'orderId' in res_short.keys():
                                        self.logger.info('%s/%s 盈利平空全仓失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                        continue
                                    else:
                                        self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                        self.redisClient.delKey("{}_short_qty".format(self.token))

                                _lowest_price = min(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))))
                                self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), _lowest_price)

                                _win = (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                                self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                                self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)

                                self.logger.info('%s/%s 清仓, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol,
                                    self.side,
                                    float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))),
                                    float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))),
                                    (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600, PublicModels.changeTime(time.time())))

                                _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                self.logger.info(_env)

                            # 当前浮盈加仓又 Bug 当价格被拉低时则会使用超低价格购入
                            # ex: 20002.0 <= 20598.0 * (1 - 0.6 / 100)
                            elif condition:
                                # 当前价格如果 大于 购买价格的 profit% 则进行浮盈加仓一次
                                if float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_base_price_{}".format(self.token, self.direction))) * (1 - self.profit):

                                    # 判断上一次下单间隔, 如果未到达跳出当前判断
                                    if time.time() - float(self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction))) < self.order_interval:
                                        continue

                                    self.logger.info('{}/{} 浮盈加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                                    res_short = trade.open_order(self.symbol, 'SELL', float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='SHORT').json()

                                    if not 'orderId' in res_short.keys():
                                        if res_short['msg'] == 'Margin is insufficient.':
                                            self.logger.info('%s/%s 浮盈加仓,可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                        else:
                                            self.logger.info('%s/%s 浮盈加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                        continue
                                    else:
                                        self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                        self.redisClient.lpushKey("{}_short_qty".format(self.token), self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction)))
                                        self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                                        _avg = (Decimal(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) + Decimal(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))))) / 2
                                        self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), float(_avg))
                                    
                                    # 计算开单均价
                                    _avg_tmp = (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) / [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)][0] + float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))) / (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) / [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)][0] + 1)
                                    self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), _avg_tmp)
                                    _base_price = (1 - self.profit) * float(self.redisClient.getKey("{}_base_price_{}".format(self.token, self.direction)))
                                    self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), _base_price)
                                    _win = ([float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)][-1] * float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) * 4e-4) - float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                                    self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)

                                    self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                        self.symbol, 
                                        self.side, 
                                        float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_tmp_{}".format(self.token, self.direction))), 
                                        float(self.redisClient.getKey("{}_avg_tmp_{}".format(self.token, self.direction))), 
                                        float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))), 
                                        float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))),
                                        float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))), 
                                        (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600, 
                                        PublicModels.changeTime(time.time())))

                                    _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                    self.logger.info(_env)

                        elif int(self.redisClient.llenKey("{}_short_qty".format(self.token))) <= 1 and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 - 0.003):
                            self.logger.info('{}/{} 平老单一次仓位 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                            if int(self.redisClient.llenKey("{}_real_short_qty".format(self.token))) == 0:
                                self.logger.info('%s/%s 平老单一次仓位失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                continue

                            # 下单平仓
                            res_short = trade.open_order(self.symbol, 'BUY', [float(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)][-1], price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='SHORT').json()

                            # 判断下单平仓
                            if not 'orderId' in res_short.keys():
                                self.logger.info('{}/{} 平老单一次仓位失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                continue
                            else:
                                self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_short["orderId"], 'SHORT', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_short))
                                nums = float(self.redisClient.brpopKey("{}_short_qty".format(self.token))[1])
                            
                            _win = (nums * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                            if int(self.redisClient.llenKey("{}_short_qty".format(self.token))) == 0:
                                self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)
                            else:
                                self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))

                            self.logger.info('%s/%s 剩余仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                self.symbol,
                                self.side,
                                float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))),
                                float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))),
                                (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600,
                                PublicModels.changeTime(time.time())))

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                            self.logger.info(_env)

                # 如果策略为开 多 时
                else:
                    self.logger.info('{}/{} U本位合约正在运行, 当前价格 {} , 已购买币种总数 {} , 已经下单总次数 {} \t {}'.format(
                        self.symbol,
                        self.side,
                        float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))),
                        float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])),
                        float(self.redisClient.llenKey("{}_long_qty".format(self.token))),
                        PublicModels.changeTime(time.time())))

                    # 判断当前价格 小于/等于 前 100 根 k 线的最小值
                    buy_condition1 = float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= (min(price1m_low[-3:]) + max(price1m_high[-3:])) / 2
                    
                    # 当起始位为 0, 则没有任何开单
                    if int(self.redisClient.llenKey("{}_long_qty".format(self.token))) == 0:

                        # 判断当前价格
                        if buy_condition1:
                            # 判断上一次下单间隔, 如果未到达跳出当前判断
                            if time.time() - float(self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction))) < self.order_interval:
                                continue

                            self.logger.info('{}/{} 下单开多, 下单数量 {}, 下单价格 {} {}'.format(
                                self.symbol,
                                self.side,
                                float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))),
                                PublicModels.changeTime(time.time())))

                            # 下单开多
                            res_long = trade.open_order(self.symbol, 'BUY', float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                            # 判断是否下单成功
                            if not 'orderId' in res_long.keys():
                                self.logger.info('{}/{} 下单开多失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                continue
                            else:
                                self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                self.redisClient.lpushKey("{}_long_qty".format(self.token), self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())

                            
                            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))
                            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))
                            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))
                            _win = (float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))) * float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) * 4e-4) - float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)

                            # 开单成功后
                            self.logger.info('%s/%s 当前仓位成本=%.1f, 开仓价=%.3f \t %s' % (
                                self.symbol,
                                self.side,
                                float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                PublicModels.changeTime(time.time())))

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction)
                            self.logger.info(_env)

                    # 判断起始位大于 0, 至少开过一次仓
                    elif int(self.redisClient.llenKey("{}_long_qty".format(self.token))) > 0:
                        # 判断当前 开单数量 是否小于 最大可开单值
                        condition = float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)])) / self.min_qty < self.max_add_times
                        # 判断 没有亏损 && (not 开单数量上限) && 当前价格 小于等于 最新下单价格 * (1 - 容忍爆仓率 * 持仓数量比)
                        if self.if_loss and (not condition) and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) * (1 - self.add_rate * np.log(1 + int(self.redisClient.llenKey("{}_long_qty".format(self.token))))):
                            self.logger.info('{}/{} 平多止损 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                            if int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))) == 0:
                                self.logger.info('%s/%s 平多失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                continue

                            if int(self.redisClient.llenKey("{}_long_qty".format(self.token))) > int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))):
                                res_long = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()

                                if not 'orderId' in res_long.keys():
                                    self.logger.info('%s/%s 平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    # 因使用 _real_long_qty 作为清仓对象则需要与 _long_qty 进行同步清除数据
                                    _real_long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)]
                                    _long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)]

                                    for order_price in _real_long_qty:
                                        _check_number = toolsMethod.checkListDetermine(_long_qty, order_price)
                                        if _check_number[0]:
                                            for index, item in enumerate(_check_number[1]):
                                                self.redisClient.lremKey("{}_long_qty".format(token), item, _check_number[2][index])

                                    _win = (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                            else:
                                res_long = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()

                                if not 'orderId' in res_long.keys():
                                    self.logger.info('%s/%s 平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    self.redisClient.delKey("{}_long_qty".format(self.token))
                                    _win = (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))

                            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                            self.logger.info(_env)

                        # 当前价格小于购买价格时的比例价格则进行 虚亏加仓
                        # 亏本达到 add_rate% * 持仓数量 时进行虚亏加仓, 判定值根据持仓单的数据进行上下浮动
                        elif condition and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) * (1 - self.add_rate * np.log(1 + int(self.redisClient.llenKey("{}_long_qty".format(self.token))))):

                            # 判断上一次下单间隔, 如果未到达跳出当前判断
                            if time.time() - float(self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction))) < self.order_interval:
                                continue

                            if float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))) * (1 + (1 - float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))) / float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction)))) / 5):

                                self.logger.info('{}/{} 虚亏加仓 {} {}'.format(self.symbol, self.side, float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])), PublicModels.changeTime(time.time())))

                                res_long = trade.open_order(self.symbol, 'BUY', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                                if not 'orderId' in res_long.keys():
                                    if res_long['msg'] == 'Margin is insufficient.':
                                        self.logger.info('%s/%s 虚亏加仓失败, 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    else:
                                        self.logger.info('%s/%s 虚亏加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    self.redisClient.lpushKey("{}_long_qty".format(self.token), float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])))
                                    self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())

                                _lowest_price = min(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), float(self.redisClient.getKey("{}_lowest_price_{}".format(self.token, self.direction))))
                                self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), _lowest_price)
                            
                                #_avg = (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) + float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))) / 2
                                #self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), _avg)
                                _avg = (Decimal(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) + Decimal(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))))) / 2
                                self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), float(_avg))
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))))
                                
                                _win = ([float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)][-1] * float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) * 4e-4) - float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)

                                self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮亏=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                    self.symbol, 
                                    self.side, 
                                    float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))), 
                                    float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                    float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))),
                                    float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))),
                                    float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))),
                                    (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600,
                                    PublicModels.changeTime(time.time())))

                                _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                self.logger.info(_env)

                        elif (not condition) and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_last_trade_price_{}".format(self.token, self.direction))) * (1 - self.add_rate * np.log(1 + int(self.redisClient.llenKey("{}_long_qty".format(self.token))))):
                            self.logger.info('{}/{} 重新开始下一轮 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                            if int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))) == 0:
                                self.logger.info('%s/%s 重新开始下一轮失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                continue

                            if int(self.redisClient.llenKey("{}_long_qty".format(self.token))) > int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))):
                                _sell_number = [Decimal(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)]

                                res_long = trade.open_order(self.symbol, 'SELL', float(sum(_sell_number[-2:])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.min_profit), self.price_precision), positionSide='LONG').json()
                                if not 'orderId' in res_long.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败1 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    # 因使用 _real_long_qty 作为清仓对象则需要与 _long_qty 进行同步清除数据
                                    _real_long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)]
                                    _long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)]

                                    for order_price in _real_long_qty[-2:]:
                                        _check_number = toolsMethod.checkListDetermine(_long_qty, order_price)
                                        if _check_number[0]:
                                            for index, item in enumerate(_check_number[1]):
                                                self.redisClient.lremKey("{}_long_qty".format(token), item, _check_number[2][index])

                                res_long = trade.open_order(self.symbol, 'SELL', float(sum(_sell_number[:-2])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.min_profit), self.price_precision), positionSide='LONG').json()
                                if not 'orderId' in res_long.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败2 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    # 因使用 _real_long_qty 作为清仓对象则需要与 _long_qty 进行同步清除数据
                                    _real_long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)]
                                    _long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)]
                                    
                                    for order_price in _real_long_qty[:-2]:
                                        _check_number = toolsMethod.checkListDetermine(_long_qty, order_price)
                                        if _check_number[0]:
                                            for index, item in enumerate(_check_number[1]):
                                                self.redisClient.lremKey("{}_long_qty".format(token), item, _check_number[2][index])
                            else:
                                _sell_number = [Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)]

                                res_long = trade.open_order(self.symbol, 'SELL', float(sum(_sell_number[-2:])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.min_profit), self.price_precision), positionSide='LONG').json()
                                if not 'orderId' in res_long.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败1 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    for item in _sell_number[-2:]:
                                        self.redisClient.brpopKey("{}_long_qty".format(self.token))

                                res_long = trade.open_order(self.symbol, 'SELL', float(sum(_sell_number[:-2])), price=round(float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.profit), self.price_precision), positionSide='LONG').json()
                                if not 'orderId' in res_long.keys():
                                    self.logger.info('%s/%s 重新开始下一轮失败2 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                else:
                                    self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                    for item in _sell_number[:-2]:
                                        self.redisClient.blpopKey("{}_long_qty".format(self.token))

                            self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0)
                            self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                            self.logger.info(_env)

                        # 当前价格如果大于 利润 profit% 或者大于 self.min_profit 即可进行盈利平多或加仓
                        elif int(self.redisClient.llenKey("{}_long_qty".format(self.token))) == 1 and (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.profit) or (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + self.min_profit) and float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))) > 0)):

                            # 最高处回调达到止盈位置则减仓一次
                            # 当盈利大于 0.00128 时就可以进行减仓所有
                            if float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) <= float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))) * (1 - (float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))) / float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) - 1) / 5):  # 重仓情形考虑回本平一半或平xx%的仓位, 待计算, 剩下依然重仓考虑吃多少点清仓
                                self.logger.info('{}/{} 盈利平多全仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                                if int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))) == 0:
                                    self.logger.info('%s/%s 盈利平多全仓失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                    continue

                                if int(self.redisClient.llenKey("{}_long_qty".format(self.token))) > int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))):

                                    res_long = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                                    if not 'orderId' in res_long.keys():
                                        self.logger.info('%s/%s 盈利平多全仓平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                        continue
                                    else:
                                        self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                        # 因使用 _real_long_qty 作为清仓对象则需要与 _long_qty 进行同步清除数据
                                        _real_long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_real_long_qty".format(self.token), 0, -1)]
                                        _long_qty = [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)]

                                        for order_price in _real_long_qty:
                                            _check_number = toolsMethod.checkListDetermine(_long_qty, order_price)
                                            if _check_number[0]:
                                                for index, item in enumerate(_check_number[1]):
                                                    self.redisClient.lremKey("{}_long_qty".format(token), item, _check_number[2][index])
                                else:
                                    res_long = trade.open_order(self.symbol, 'SELL', float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                                    if not 'orderId' in res_long.keys():
                                        self.logger.info('%s/%s 盈利平多全仓平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                        continue
                                    else:
                                        self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                        self.redisClient.delKey("{}_long_qty".format(self.token))

                                _highest_price = max(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), float(self.redisClient.getKey("{}_highest_price_{}".format(self.token, self.direction))))
                                self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), _highest_price)

                                _win = (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                                self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                                self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)

                                self.logger.info('%s/%s 清仓, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t%s' % (
                                    self.symbol, 
                                    self.side, 
                                    float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))), 
                                    float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))), 
                                    (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600, 
                                    PublicModels.changeTime(time.time())))

                                _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                self.logger.info(_env)

                            elif condition:
                                # 当前价格如果 大于 购买价格的 profit% 则进行浮盈加仓一次
                                if float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_base_price_{}".format(self.token, self.direction))) * (1 + self.profit):
                                    # 判断上一次下单间隔, 如果未到达跳出当前判断
                                    if time.time() - float(self.redisClient.getKey("{}_last_order_time_{}".format(self.token, self.direction))) < self.order_interval:
                                        continue

                                    self.logger.info('{}/{} 浮盈加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                                    res_long = trade.open_order(self.symbol, 'BUY', float(self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction))), price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                                    if not 'orderId' in res_long.keys():
                                        if res_long['msg'] == 'Margin is insufficient.':
                                            self.logger.info('%s/%s 浮盈加仓失败, 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                        else:
                                            self.logger.info('%s/%s 浮盈加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                        continue
                                    else:
                                        self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                        self.redisClient.lpushKey("{}_long_qty".format(self.token), self.redisClient.getKey("{}_position_size_{}".format(self.token, self.direction)))
                                        self.redisClient.setKey("{}_last_order_time_{}".format(self.token, self.direction), time.time())
                                        _avg = (Decimal(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) + Decimal(float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))))) / 2
                                        self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), float(_avg))

                                    #if float(self.redisClient.getKey("{}_base_price_{}".format(self.token, self.direction))) > float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))):
                                    #    self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_tmp_{}".format(self.token, self.direction)))
                                    # 计算开单均价
                                    _avg_tmp = (float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) / [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)][0] + float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction)))) / (float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) / [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)][0] + 1)
                                    self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), _avg_tmp)

                                    _base_price = (1 + self.profit) * float(self.redisClient.getKey("{}_base_price_{}".format(self.token, self.direction)))
                                    self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), _base_price)
                                    _win = ([float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)][-1] * float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) * 4e-4) - float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                                    self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                                    

                                    self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                        self.symbol, 
                                        self.side, 
                                        float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_tmp_{}".format(self.token, self.direction))), 
                                        float(self.redisClient.getKey("{}_avg_tmp_{}".format(self.token, self.direction))), 
                                        float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))), 
                                        float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))),
                                        float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))), 
                                        (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600, 
                                        PublicModels.changeTime(time.time())))

                                    _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                    self.logger.info(_env)

                        ## 止盈最近的一次开仓
                        ## 判断已经开单且 当前价格 >= 开单价格 * (1 + 0.003)
                        elif int(self.redisClient.llenKey("{}_long_qty".format(self.token))) >= 1 and float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) >= float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))) * (1 + 0.003):

                            self.logger.info('{}/{} 平老单一次仓位 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))

                            if int(self.redisClient.llenKey("{}_real_long_qty".format(self.token))) == 0:
                                self.logger.info('%s/%s 平老单一次仓位失败, 没有仓位可平 \t %s' % (self.symbol, self.side, PublicModels.changeTime(time.time())))
                                continue

                            res_long = trade.open_order(self.symbol, 'SELL', [float(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)][-1], price=float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))), positionSide='LONG').json()
                            if not 'orderId' in res_long.keys():
                                self.logger.info('%s/%s 平老单一次仓位失败 \t %s \t %s' % (
                                    self.symbol,
                                    self.side,
                                    str(res_long),
                                    PublicModels.changeTime(time.time())))
                                _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                                self.logger.info(_env)
                                continue
                            else:
                                self.redisClient.setKey('{}_orderId_{}_{}_{}'.format(self.token, res_long["orderId"], 'LONG', PublicModels.changeTimeNoTabs(time.time())), json.dumps(res_long))
                                nums = float(self.redisClient.brpopKey("{}_long_qty".format(self.token))[1])

                            _win = (nums * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))) * (1 - 4e-4)) + float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction)))
                            self.redisClient.setKey("{}_win_{}".format(self.token, self.direction), _win)
                            self.redisClient.setKey("{}_highest_price_{}".format(self.token, self.direction), 0.0)
                            self.redisClient.setKey("{}_lowest_price_{}".format(self.token, self.direction), 100000.0)
                            if int(self.redisClient.llenKey("{}_long_qty".format(self.token))) == 0:
                                self.redisClient.setKey("{}_avg_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), 0.0)
                                self.redisClient.setKey("{}_avg_tmp_{}".format(self.token, self.direction), 0.0)
                            else:
                                self.redisClient.setKey("{}_base_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))
                                self.redisClient.setKey("{}_last_trade_price_{}".format(self.token, self.direction), self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))

                            self.logger.info('%s/%s 剩余仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                self.symbol,
                                self.side,
                                float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction))),
                                float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)])) * (float(self.redisClient.getKey("{}_present_price_{}".format(self.token, self.direction))) - float(self.redisClient.getKey("{}_avg_{}".format(self.token, self.direction)))),
                                float(self.redisClient.getKey("{}_win_{}".format(self.token, self.direction))),
                                float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))),
                                (time.time() - float(self.redisClient.getKey("{}_t_start_{}".format(self.token, self.direction)))) / 3600,
                                PublicModels.changeTime(time.time())))

                            _env = toolsMethod.checkRedisKeyValues(self.redisClient, self.token, self.direction, condition)
                            self.logger.info(_env)

                _max_position = max(
                    float(self.redisClient.getKey("{}_max_position_{}".format(self.token, self.direction))),
                    float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_short_qty".format(self.token), 0, -1)])),
                    float(sum([Decimal(item) for item in self.redisClient.lrangeKey("{}_long_qty".format(self.token), 0, -1)]))) / self.min_qty
                
                self.redisClient.setKey("{}_max_position_{}".format(self.token, self.direction), _max_position)

            except Exception as err:
                self.logger.error("异常错误 {} 已忽略 {}".format(err, PublicModels.changeTime(time.time())))

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'symbol': args.symbol, 'key': args.key, 'secret': args.secret, 'token': args.token}
    
    p1 = Process(target=globalSetOrderIDStatus, args=(args.symbol, args.key, args.secret, args.token,))
    gs = GridStrategy(**conn_setting)
    p1.start()
    gs.run()
    gs.join()
    p1.join()
