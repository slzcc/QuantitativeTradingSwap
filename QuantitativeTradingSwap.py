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
from utils.QuantitativeTradingSwapUtils import command_line_args
from logging.handlers import TimedRotatingFileHandler

class GridStrategy:
    def __init__(self, symbol, key, secret):
        """
        :param symbol: BTC
        :param price_precision: 2
        :param qty_precision: 4
        :param min_qty: 最小开仓数量
        :param profit: 清仓波动
        :param add_rate: 加仓间隔，%
        :param add_times: 加仓倍率, 默认2倍
        :param T: 前高/低周期长度, 默认取1min计近似最优参
        """
        self.key = key                  # 用户凭证
        self.secret = secret            # 用户凭证
        self.name = symbol              # 开单名称
        self.step = 0                   # 开单后多单会 -1, 空单会 +1
        self.symbol = symbol[:-1]       # 获取对币种进行切割如 ETHUSDT多 取 ETHUSDT
        self.side = symbol[-1]          # 获取对币种进行切割如 ETHUSDT多 取 多
        self.avg = 0.0
        self.buy_qty = []               # 开空下单池
        self.sell_qty = []              # 开多下单池
        self.win = 0.0
        self.last_buy = 0.0             # 开多时的购买价格
        self.last_sell = 0.0            # 开空时的购买价格
        self.lowest_price = 100000.0    # 记录最低价用于加仓参考
        self.highest_price = 0.0        # 记录最高价
        self.base_price = 0.0           # 记录正加仓
        self.avg_tmp = 0.0              # 延迟记录均价变化(开单均价)
        self.max_position = 0           # 记录实盘最大仓位, 供后续参考
        self.t_start = time.time()      # 开始时间
        self.read_conf(symbol)

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

        # 如果日志目录不存在进行创建
        if not os.path.exists('logs'):
            os.mkdir('logs')

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

    def grid_run(self):
        # 获取一个 Binance API 对象
        trade = tradeAPI.TradeApi(self.key, self.secret)
        # 更改持仓方式，默认单向
        checkAccount = trade.change_side(False).json()
        if "code" in checkAccount.keys():
            if checkAccount["code"] != -4059:
                raise AssertionError("账户凭证存在异常, 返回内容 {}, 请检查后继续!".format(checkAccount))

        # 变换逐全仓, 默认逐仓
        trade.change_margintype(self.symbol, isolated=False).json()
        # 调整开仓杠杆
        trade.set_leverage(self.symbol, self.position_times).json()
        # 设置当前启动时间
        t_start = time.time()
        self.logger.info('{}/{} U本位开始运行 \t {} \t #################'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
        while True:
            try:
                # 获取 1m 时间的 k 线
                klines = get_history_k(typ='futures', coin=self.symbol, T='1m').json()
                # 获取 k 线中最低的价格(取每个 list 中第 3 个位置数据)
                price1m_low = list(map(lambda x: float(x[3]), klines))
                # 获取 k 线中最高的价格(取每个 list 中第 2 个位置数据)
                price1m_high = list(map(lambda x: float(x[2]), klines))
                # 记录最小购买单价
                self.position_size = self.min_qty
                try:
                    # 获取 k 线中现在的价格(第一个价格)
                    self.present_price = float(klines[-1][4])
                except:
                    # 获取最新价格
                    # 有请求延迟
                    self.present_price = float(get_present_price('{}'.format(self.symbol)).json()['price'])
                # 如果策略为开 空 时
                if self.side != '多':
                    self.logger.info('{}/{} U本位合约正在运行, 当前价格 {} , 已购买币种总数 {} , 已经下单总次数 {} , 锚点位置 {} \t {}'.format(
                        self.symbol, self.side, self.present_price, sum(self.buy_qty), len(self.buy_qty), self.step, PublicModels.changeTime(time.time())))
                    # 起始位置 0, 且没有开仓
                    if self.step == 0:
                        # 判断当前价格 大于/等于 前 500 根 k 线的最大值
                        sell_condition1 = self.present_price >= max(price1m_low[:500])
                        # 判断当前价格 小于/等于 后 500 根 k 线的最小值
                        sell_condition2 = self.present_price <= max(price1m_high[-500:])

                        # 判断数据是否为空
                        if sell_condition1 and sell_condition2:
                            self.logger.info('{}/{} 下单开空 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            # 下单开空, 市价开单
                            res_short = trade.open_order(self.symbol, 'SELL', self.position_size, price=self.present_price, positionSide='SHORT').json()
                            # 判断下单是否成功
                            if not 'orderId' in res_short:
                                self.logger.info('{}/{} 开空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                continue

                            # 记录开仓价格
                            self.avg = self.present_price
                            # 记录起始价格
                            self.base_price = self.present_price
                            # 记录出售价格
                            self.last_sell = self.present_price
                            # 记录购买数量到 buy_qty 列表中
                            self.buy_qty.append(self.position_size)
                            # 锚点计数开空 -1
                            self.step -= 1
                            # 科学记数法到十进制 https://calculator.name/scientific-notation-to-decimal
                            # 4e-4 等于 4/10000
                            # 记录止损值(值是购买币的数量)
                            self.win -= self.position_size * self.present_price * 4e-4
                            # 下单成功
                            self.logger.info('%s/%s 当前仓位成本=%.1f, 开仓价=%.3f \t %s' % (self.symbol, self.side, sum(self.buy_qty) * self.avg, self.avg, PublicModels.changeTime(time.time())))

                    # 当锚点为负数时, 证明已下过单
                    elif self.step < 0:
                        # 判断是否可以继续下单，返回布尔值
                        # 开仓总币价 / 每单币价 < 开仓数量
                        condition = sum(self.buy_qty) / self.min_qty < self.max_add_times
                        # 判断 仓位 是否需要进行止损(全仓平仓)
                        ## 判断 亏损 && (是否可以继续开仓) && 当前价格 大于等于 准备出售价格 乘以 (1 + 1.2 * 开仓数量比例值) ep: 19700.0 * (1 + 1.2 * np.log(1 - -1))
                        ## 主要判断亏损如果超过范围则进行止损平仓（开仓数量到达上限）
                        if self.if_loss and (not condition) and self.present_price >= self.last_sell * (1 + self.add_rate * np.log(1 - self.step)):
                            self.logger.info('{}/{} 平空止损 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                            self.logger.info(_env)
                            _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                            self.logger.info(_env2)
                            self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_sell * (1 + self.add_rate * np.log(1 - self.step))))

                            # 下单平空(市价平所有仓位)
                            res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty), price=self.present_price, positionSide='SHORT').json()
                            # 判断下单平空
                            if not 'orderId' in res_long:
                                self.logger.info('{}/{} 平空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                continue

                            # 记录止损值(值是购买U的数量)
                            self.win += sum(self.buy_qty) * (self.avg - self.present_price) * (1 - 4e-4)
                            # 锚点 0
                            self.step = 0
                            # 均价 0
                            self.avg = 0.0
                            # 最新购买 0
                            self.last_sell = 0.0
                            # 购买池 0
                            self.buy_qty = []
                            # 最小购买值(暂时无用)
                            self.lowest_price = 100000.0
                            # 最高价 0
                            self.highest_price = 0.0
                            # 基础价格 0
                            self.base_price = 0.0
                            # 延迟记录均价变化 0
                            self.avg_tmp = 0.0

                        ## 如果仓位亏损继续扩大则到达比例后进行加仓
                        ## 判断是否可以加仓
                        elif condition and self.present_price >= self.last_sell * (1 + self.add_rate * np.log(1 - self.step)):
                            self.highest_price = max(self.present_price, self.highest_price)
                            if self.present_price <= self.highest_price * (1 - (self.highest_price / self.last_sell - 1) / 5):
                                self.logger.info('{}/{} 虚亏加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                                _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                                self.logger.info(_env)
                                _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                                self.logger.info(_env2)
                                self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_sell * (1 + self.add_rate * np.log(1 - self.step))))
                                # 下单加仓
                                res_short = trade.open_order(self.symbol, 'SELL', sum(self.buy_qty), price=self.present_price, positionSide='SHORT').json()
                                # 判断下单加仓
                                if not 'orderId' in res_short:
                                    if res_short['msg'] == 'Margin is insufficient.':
                                        self.logger.info('{}/{} 可用金不足 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    else:
                                        self.logger.info('{}/{} 加仓失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue

                                self.avg = (self.avg + self.present_price) / 2
                                self.last_sell = self.present_price
                                self.buy_qty.append(sum(self.buy_qty))
                                self.step -= 1
                                self.win -= self.buy_qty[-1] * self.present_price * 4e-4

                                self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮亏=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t%s' % (
                                    self.symbol, self.side, sum(self.buy_qty) * self.avg, self.avg, sum(self.buy_qty) * (self.avg - self.present_price), self.win,
                                    self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                        ## 如果仓位盈利且到达阀值后进行止盈平仓
                        ## 判断 not condition 能继续开仓且 当前最新价格 >= 购买价格 * (1 + 加减仓百分比阀值 * 下单数量的自然对数)
                        ## 第一单盈利大于 0.00566 左右就可以盈利清仓
                        elif (not condition) and self.present_price >= self.last_sell * (1 + self.add_rate * np.log(1 - self.step)):
                            # 给本轮马丁挂上止盈, 重置重新开始下一轮
                            self.logger.info('{}/{} 重新开始下一轮 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                            self.logger.info(_env)
                            _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                            self.logger.info(_env2)
                            self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_sell * (1 + self.add_rate * np.log(1 - self.step))))

                            res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty[-2:]), price=round(self.avg * (1 - self.min_profit), self.price_precision), positionSide='SHORT').json()
                            res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty[:-2]), price=round(self.avg * (1 - self.profit), self.price_precision), positionSide='SHORT').json()

                            self.step = 0
                            self.avg = 0.0
                            self.last_sell = 0.0
                            self.buy_qty = []
                            self.lowest_price = 100000.0
                            self.highest_price = 0.0
                            self.base_price = 0.0
                            self.avg_tmp = 0.0

                        # 判断 第一次开仓后 && (当前价格 小于等于 购买价格 * (1 - self.min_profit)) && 最低价格 < 100000
                        elif self.step == -1 and (self.present_price <= self.avg * (1 - self.profit) or (self.present_price <= self.avg * (1 - self.min_profit) and self.lowest_price < 100000)):
                            self.lowest_price = min(self.present_price, self.lowest_price)
                            if self.present_price >= self.lowest_price * (1 + (1 - self.lowest_price / self.avg) / 5):
                                self.logger.info('{}/{} 盈利平空 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                                _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                                self.logger.info(_env)
                                _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                                self.logger.info(_env2)
                                self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_sell * (1 + self.add_rate * np.log(1 - self.step))))

                                res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty), price=self.present_price, positionSide='SHORT').json()
                                if not 'orderId' in res_long:
                                    self.logger.info('%s/%s 平空失败 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue

                                self.win += sum(self.buy_qty) * (self.avg - self.present_price) * (1 - 4e-4)
                                self.step = 0
                                self.avg = 0.0
                                self.last_sell = 0.0
                                self.buy_qty = []
                                self.lowest_price = 100000.0
                                self.highest_price = 0.0
                                self.base_price = 0.0
                                self.avg_tmp = 0.0

                                self.logger.info('%s/%s 清仓, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                            else:
                                if self.present_price <= self.base_price * (1 - self.profit):
                                    if self.base_price < self.avg:
                                        self.avg = self.avg_tmp
                                    self.avg_tmp = (self.avg * sum(self.buy_qty) / self.buy_qty[0] + self.present_price) / (sum(self.buy_qty) / self.buy_qty[0] + 1)

                                    self.logger.info('{}/{} 浮盈加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                                    _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                                    self.logger.info(_env)
                                    _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                                    self.logger.info(_env2)
                                    self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_sell * (1 + self.add_rate * np.log(1 - self.step))))

                                    res_short = trade.open_order(self.symbol, 'SELL', self.buy_qty[0], price=self.present_price, positionSide='SHORT').json()
                                    if not 'orderId' in res_short:
                                        if res_short['msg'] == 'Margin is insufficient.':
                                            self.logger.info('%s/%s 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                        else:
                                            self.logger.info('%s/%s 加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                        continue

                                    self.base_price *= 1 - self.profit
                                    self.buy_qty.append(self.buy_qty[0])
                                    self.win -= self.buy_qty[-1] * self.present_price * 4e-4

                                    self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                        self.symbol, self.side, sum(self.buy_qty) * self.avg_tmp, self.avg_tmp, sum(self.buy_qty) * (self.present_price - self.avg), self.win,
                                        self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                        elif self.step < -1 and self.present_price <= self.avg * (1 - 0.003):
                            self.logger.info('{}/{} 平最近一次加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                            self.logger.info(_env)
                            _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                            self.logger.info(_env2)
                            self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.avg * (1 - 0.003)))

                            # 下单平仓
                            res_long = trade.open_order(self.symbol, 'BUY', self.buy_qty[-1], price=self.present_price, positionSide='SHORT').json()
                            # 判断下单平仓
                            if not 'orderId' in res_long:
                                self.logger.info('{}/{} 平空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                continue

                            nums = self.buy_qty.pop()
                            self.win += nums * (self.avg - self.present_price) * (1 - 4e-4)
                            self.step = -1
                            self.base_price = self.avg
                            self.highest_price = 0.0
                            self.last_sell = self.avg

                            self.logger.info('%s/%s 剩余仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, sum(self.buy_qty)*self.avg, self.avg, sum(self.buy_qty) * (self.avg - self.present_price), self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                # 如果策略为开 多 时
                else:
                    self.logger.info('{}/{} U本位合约正在运行, 当前价格 {} , 已购买币种总数 {} , 已经下单总次数 {} , 锚点位置 {} \t {}'.format(
                        self.symbol, self.side, self.present_price, sum(self.sell_qty), len(self.sell_qty), self.step, PublicModels.changeTime(time.time())))
                    # 当起始位为 0, 则没有任何开单
                    if self.step == 0:

                        # 判断当前价格 小于/等于 前 100 根 k 线的最小值
                        buy_condition1 = self.present_price <= min(price1m_low[:100])

                        # 判断当前价格
                        if buy_condition1:
                            self.logger.info('{}/{} 开多 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            # 下单开多
                            res_long = trade.open_order(self.symbol, 'BUY', self.position_size, price=self.present_price, positionSide='LONG').json()
                            # 判断是否下单成功
                            if not 'orderId' in res_long:
                                self.logger.info('{}/{} 开多失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                continue

                            self.avg = self.present_price
                            self.base_price = self.avg
                            self.sell_qty.append(self.position_size)
                            self.step += 1
                            self.last_buy = self.present_price
                            self.win -= self.position_size * self.present_price * 4e-4

                            # 开单成功后
                            self.logger.info('%s/%s 当前仓位成本=%.1f, 开仓价=%.3f \t %s' % (self.symbol, self.side, sum(self.sell_qty) * self.avg, self.avg, PublicModels.changeTime(time.time())))

                    # 判断起始位大于 0, 至少开过一次仓
                    elif self.step > 0:
                        # 判断当前 开单数量 是否小于 最大可开单值
                        condition = sum(self.sell_qty) / self.min_qty < self.max_add_times
                        # 判断 没有亏损 && (not 开单数量上限) && 当前价格 小于等于 最新下单价格 * (1 - 容忍爆仓率 * 持仓数量比)
                        if self.if_loss and (not condition) and self.present_price <= self.last_buy * (1 - self.add_rate * np.log(1 + self.step)):
                            self.logger.info('{}/{} 平多止损 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                            self.logger.info(_env)
                            _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                            self.logger.info(_env2)
                            self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_buy * (1 - self.add_rate * np.log(1 + self.step))))

                            res_short = trade.open_order(self.symbol, 'SELL', sum(self.sell_qty), price=self.present_price, positionSide='LONG').json()
                            if not 'orderId' in res_short:
                                self.logger.info('%s/%s 平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                continue

                            self.win += sum(self.sell_qty) * (self.present_price - self.avg) * (1 - 4e-4)
                            self.step = 0
                            self.avg = 0.0
                            self.last_buy = 0.0
                            self.sell_qty = []
                            self.lowest_price = 100000.0
                            self.highest_price = 0.0
                            self.base_price = 0.0
                            self.avg_tmp = 0.0

                        # 当前价格小于购买价格时的比例价格则进行 虚亏加仓
                        # 亏本达到 add_rate% * 持仓数量 时进行虚亏加仓, 判定值根据持仓单的数据进行上下浮动
                        elif condition and self.present_price <= self.last_buy * (1 - self.add_rate * np.log(1 + self.step)):
                            self.lowest_price = min(self.present_price, self.lowest_price)
                            if self.present_price >= self.lowest_price * (1 + (1 - self.lowest_price / self.last_buy) / 5):
                                self.logger.info('{}/{} 虚亏加仓 {} {}'.format(self.symbol, self.side, sum(self.sell_qty), PublicModels.changeTime(time.time())))
                                _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                                self.logger.info(_env)
                                _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                                self.logger.info(_env2)
                                self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_buy * (1 - self.add_rate * np.log(1 + self.step))))

                                res_long = trade.open_order(self.symbol, 'BUY', sum(self.sell_qty), price=self.present_price, positionSide='LONG').json()
                                if not 'orderId' in res_long:
                                    if res_long['msg'] == 'Margin is insufficient.':
                                        self.logger.info('%s/%s 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    else:
                                        self.logger.info('%s/%s 加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue

                                self.avg = (self.avg + self.present_price) / 2
                                self.last_buy = self.present_price
                                self.sell_qty.append(sum(self.sell_qty))
                                self.step += 1
                                self.win -= self.sell_qty[-1] * self.present_price * 4e-4

                                self.logger.info('%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮亏=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, sum(self.sell_qty) * self.avg, self.avg,
                                        sum(self.sell_qty) * (self.present_price - self.avg), self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                        elif (not condition) and self.present_price <= self.last_buy * (1 - self.add_rate * np.log(1 + self.step)):
                            self.logger.info('{}/{} 重新开始下一轮 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                            self.logger.info(_env)
                            _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                            self.logger.info(_env2)
                            self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_buy * (1 - self.add_rate * np.log(1 + self.step))))

                            trade.open_order(self.symbol, 'SELL', sum(self.sell_qty[-2:]), price=round(self.avg * (1 + self.min_profit), self.price_precision), positionSide='LONG').json()
                            trade.open_order(self.symbol, 'SELL', sum(self.sell_qty[:-2]), price=round(self.avg * (1 + self.profit), self.price_precision), positionSide='LONG').json()

                            self.step = 0
                            self.avg = 0.0
                            self.last_buy = 0.0
                            self.sell_qty = []
                            self.lowest_price = 100000.0
                            self.highest_price = 0.0
                            self.base_price = 0.0
                            self.avg_tmp = 0.0

                        # 当前价格如果大于 利润 profit% 或者大于 self.min_profit 即可进行盈利平多或加仓
                        elif self.step == 1 and (self.present_price >= self.avg * (1 + self.profit) or (self.present_price >= self.avg * (1 + self.min_profit) and self.highest_price > 0)):
                            self.highest_price = max(self.present_price, self.highest_price)
                            # 最高处回调达到止盈位置则减仓一次
                            # 当盈利大于 0.00128 时就可以进行减仓一次
                            if self.present_price <= self.highest_price * (1 - (self.highest_price / self.avg - 1) / 5):  # 重仓情形考虑回本平一半或平xx%的仓位, 待计算, 剩下依然重仓考虑吃多少点清仓
                                self.logger.info('{}/{} 盈利平多 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                                _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                                self.logger.info(_env)
                                _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                                self.logger.info(_env2)
                                self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_buy * (1 - self.add_rate * np.log(1 + self.step))))

                                res_short = trade.open_order(self.symbol, 'SELL', sum(self.sell_qty), price=self.present_price, positionSide='LONG').json()
                                if not 'orderId' in res_short:
                                    self.logger.info('%s/%s 平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue

                                self.win += sum(self.sell_qty) * (self.present_price - self.avg) * (1 - 4e-4)
                                self.step = 0
                                self.avg = 0.0
                                self.last_buy = 0.0
                                self.sell_qty = []
                                self.lowest_price = 100000.0
                                self.highest_price = 0.0
                                self.base_price = 0.0
                                self.avg_tmp = 0.0

                                self.logger.info('%s/%s 清仓, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t%s' % (self.symbol, self.side, self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                            else:
                                # 当前价格如果 大于 购买价格的 profit% 则进行浮盈加仓一次
                                if self.present_price >= self.base_price * (1 + self.profit):
                                    if self.base_price > self.avg:
                                        self.avg = self.avg_tmp

                                    # 计算开单均价
                                    self.avg_tmp = (self.avg * sum(self.sell_qty) / self.sell_qty[0] + self.present_price) / (sum(self.sell_qty) / self.sell_qty[0] + 1)
                                    self.logger.info('{}/{} 浮盈加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                                    _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                                    self.logger.info(_env)
                                    _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                                    self.logger.info(_env2)
                                    self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.last_buy * (1 - self.add_rate * np.log(1 + self.step))))

                                    res_long = trade.open_order(self.symbol, 'BUY', self.sell_qty[0], price=self.present_price, positionSide='LONG').json()
                                    if not 'orderId' in res_long:
                                        if res_long['msg'] == 'Margin is insufficient.':
                                            self.logger.info('%s/%s 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                        else:
                                            self.logger.info('%s/%s 加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                        continue

                                    self.base_price *= 1 + self.profit
                                    self.sell_qty.append(self.sell_qty[0])
                                    self.win -= self.sell_qty[-1] * self.present_price * 4e-4

                        ## 止盈最近的一次开仓
                        ## 判断已经开单且 当前价格 >= 开单价格 * (1 + 0.003)
                        elif self.step > 1 and self.present_price >= self.avg * (1 + 0.003):
                            self.logger.info('{}/{} 平最近一次加仓 {}'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
                            _env = '"key": {}, "secret": {}, "name": {}, "step": {}, "symbol": {}, "side": {}, "avg": {}, "buy_qty": {}, "sell_qty": {}, "win": {}, "last_buy": {}, "last_sell": {}, "lowest_price": {}, "highest_price": {}, "base_price": {}, "avg_tmp": {}, "max_position": {}, "t_start": {}, "add_rate": {}'.format(self.key, self.secret, self.name, self.step, self.symbol, self.side, self.avg, self.buy_qty, self.sell_qty, self.win, self.last_buy, self.last_sell, self.lowest_price, self.highest_price, self.base_price, self.avg_tmp, self.max_position, self.t_start, self.add_rate)
                            self.logger.info(_env)
                            _env2 = '"price_precision": {}, "qty_precision": {}, "min_qty": {}, "max_add_times": {}, "profit": {}, "add_rate": {}, "T": {}, "position_times": {}, "if_loss": {}'.format(self.price_precision, self.qty_precision, self.min_qty, self.max_add_times, self.profit, self.add_rate, self.T, self.position_times, self.if_loss)
                            self.logger.info(_env2)
                            self.logger.info('condition: {}, present_price: {}, CalculatedValue: {}'.format(condition, self.present_price, self.avg * (1 + 0.003)))

                            res_short = trade.open_order(self.symbol, 'SELL', self.sell_qty[-1], price=self.present_price, positionSide='LONG').json()
                            if not 'orderId' in res_short:
                                self.logger.info('%s/%s 平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                continue

                            nums = self.sell_qty.pop()
                            self.win += nums * (self.present_price - self.avg) * (1 - 4e-4)
                            self.step = 1
                            self.lowest_price = 100000.0
                            self.base_price = self.avg
                            self.last_buy = self.avg

                            self.logger.info('%s/%s 剩余仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                self.symbol, self.side, sum(self.sell_qty) * self.avg, self.avg, sum(self.sell_qty) * (self.present_price - self.avg), self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                self.max_position = max(self.max_position, sum(self.buy_qty), sum(self.sell_qty)) / self.min_qty
            except Exception as err:
                self.logger.error("异常错误 {} 已忽略 {}".format(err, PublicModels.changeTime(time.time())))

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'symbol': args.symbol, 'key': args.key, 'secret': args.secret}
    gs = GridStrategy(**conn_setting)
    gs.grid_run()
