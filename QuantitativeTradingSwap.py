
# 马丁微调, 设置浮亏补仓次数上限, 到达上限会挂上止盈单后启动下一轮新马丁
# 在浮盈时固定间隔加一倍底仓, 按回调率跟踪止盈, 暂定浮盈的20%，比如浮盈5%回撤至4%，可根据实际调整一个动态回调算法
# 该策略运行时长约2-3个月, 收益曲线不平稳, 实盘当时有4k+U, 1个月收益60%，从5w的饼做多到6w9, 后面持续做多, 在暴跌中, 该策略注定了吃灰的结局, 如果能看出较大的趋势波段, 此策略堪称优秀, 币本位食用更佳
import time
import json
import sys
import numpy as np
from utils.binance import tradeAPI
from utils.binance.getKlineData import *
from conf.settings import *
from utils.public import *
from utils import public as PublicModels
from utils.QuantitativeTradingSwapUtils import command_line_args

def to_log(symbol, msg):
    with open('logs/{}.log'.format(symbol),'a+') as f:
        f.write(msg + '\n')

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
        :param free_money: 限制最大本金
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
        self.avg_tmp = 0.0              # 延迟记录均价变化
        self.max_position = 0           # 记录实盘最大仓位, 供后续参考
        self.t_start = time.time()      # 开始时间
        self.read_conf(symbol)

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
        self.add_rate = arg_data['add_rate'] / 100
        self.T = arg_data['T']
        self.position_times = arg_data['position_times']
        self.if_loss = arg_data['if_loss']

    def grid_run(self):
        # 获取一个 binance api 对象
        trade = tradeAPI.TradeApi(self.key, self.secret)
        # 更改持仓模式, 默认单向
        checkAccount = trade.change_side(False)
        if "code" in checkAccount.keys():
            if checkAccount["code"] != -4059:
                raise AssertionError("账户凭证存在异常, 返回内容 {}, 请检查后继续!".format(checkAccount))
        time.sleep(1)
        # 变换逐全仓, 默认逐仓
        trade.change_margintype(self.symbol, isolated=False)
        time.sleep(1)
        # 调整开仓杠杆
        trade.set_leverage(self.symbol, self.position_times)
        time.sleep(1)
        t_start = time.time()
        to_log(self.name, '{}/{} U本位开始运行 \t {} \t #################'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
        while True:
            # 获取 币 1m 时间段的 k 线
            klines2 = get_history_k(typ='futures', coin=self.symbol, T='1m')
            # 获取 k 线中最低的价格
            price1m_low = list(map(lambda x: float(x[3]), klines2))
            # 获取 k 线中最高的价格
            price1m_high = list(map(lambda x: float(x[2]), klines2))
            # 获取 k 线中现在的价格
            self.present_price = float(klines2[-1][4])
            # 如果是起始节点, 则读取 symbol 配置文件初始化参数
            if self.step == 0:
                self.read_conf(self.symbol + self.side)
            # if time.time() // 3600 - t_start // 3600 == 1:
            #     t_start = time.time()
            to_log(self.name, '{}/{} U本位合约正在运行, 当前价格 {} \t {}'.format(self.symbol, self.side,self.present_price, PublicModels.changeTime(time.time())))
            # 记录最小购买单价
            self.position_size = self.min_qty
            # 如果策略为开 空 时
            if self.side != '多':
                # 起始位置 0, 且没有开仓
                if self.step == 0:
                    # 判断当前价格 小于/等于 后三根 k 线的最小值
                    sell_condition1 = self.present_price <= min(price1m_low[-4:-1])
                    # 判断当前价格 大于/等于 后四根 k 线的最大值
                    sell_condition2 = self.present_price >= max(price1m_high[-5:-1])

                    # 判断数据是否为空
                    if sell_condition1 or sell_condition2:
                        to_log(self.name, '{}/{} 下单开空'.format(self.symbol, self.side))
                        # 下单开空
                        res_short = trade.open_order(self.symbol, 'SELL', self.position_size, price=None, positionSide='SHORT')
                        # 判断下单是否成功
                        if not 'orderId' in res_short:
                            to_log(self.name, '{} 开空失败 \t {} \t {}'.format(self.symbol, str(res_short), PublicModels.changeTime(time.time())))
                            time.sleep(10)
                            continue

                        # 记录开仓值
                        self.avg = self.present_price
                        # 记录起始价格
                        self.base_price = self.avg
                        # 记录出售价格
                        self.last_sell = self.present_price
                        # 记录购买单价到 buy_qty 列表中
                        self.buy_qty.append(self.position_size)
                        # 起始位置 -1
                        self.step -= 1
                        # 科学记数法到十进制 https://calculator.name/scientific-notation-to-decimal
                        # 4e-4 等于 4/10000
                        self.win -= self.position_size * self.present_price * 4e-4
                        # 下单成功
                        to_log(self.name, '%s/%s 当前仓位成本=%.1f, 开仓价=%.3f\t%s' % (self.symbol, self.side, sum(self.buy_qty) * self.avg, self.avg, PublicModels.changeTime(time.time())))

                # 起始位非 0
                elif self.step < 0:
                    # 限制加仓次数, 返回布尔值
                    condition = sum(self.buy_qty) / self.min_qty < self.max_add_times
                    # 判断 仓位 是否需要进行止损(全仓平仓)
                    ## 判断 亏损 && (是否可以继续开仓) && 当前价格 大于等于 准备出售价格 乘以 (1 + 1.2 * 开仓数量比例值) ep: 19700.0 * (1 + 1.2 * np.log(1 - -1))
                    ## 主要判断亏损如果超过范围则进行止损平仓
                    if self.if_loss and (not condition) and self.present_price >= self.last_sell * (1 + self.add_rate * np.log(1 - self.step)):
                        to_log(self.name, '{}/{} 平空止损'.format(self.symbol, self.side))
                        # 下单平空(平所有仓位)
                        res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty), price=None, positionSide='SHORT')
                        # 判断下单平空
                        if not 'orderId' in res_long:
                            to_log(self.name, '{}/{} 平空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                            continue
                        self.win += sum(self.buy_qty) * (self.avg - self.present_price) * (1-4e-4)
                        self.step = 0
                        self.avg = 0.0
                        self.last_sell = 0.0
                        self.buy_qty = []
                        self.lowest_price = 100000.0
                        self.highest_price = 0.0
                        self.base_price = 0.0
                        self.avg_tmp = 0.0

                    ## 如果仓位亏损继续扩大则到达比例后进行加仓
                    ## 判断是否可以加仓
                    elif condition and self.present_price >= self.last_sell * ( 1 + self.add_rate * np.log(1 - self.step)):
                        self.highest_price = max(self.present_price, self.highest_price)
                        if self.present_price <= self.highest_price*(1-(self.highest_price/self.last_sell-1)/5):
                            to_log(self.name, '{}/{} 加仓'.format(self.symbol, self.side))
                            # 下单加仓
                            res_short = trade.open_order(self.symbol, 'SELL', sum(self.buy_qty), price=None, positionSide='SHORT')
                            # 判断下单加仓
                            if not 'orderId' in res_short:
                                if res_short['msg'] == 'Margin is insufficient.':
                                    to_log(self.name, '{}/{} 可用金不足 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                else:
                                    to_log(self.name, '{}/{} 加仓失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                continue
                            self.avg = (self.avg + self.present_price) / 2
                            self.last_sell = self.present_price
                            self.buy_qty.append(sum(self.buy_qty))
                            self.step -= 1
                            self.win -= self.buy_qty[-1] * self.present_price * 4e-4
                            to_log(self.name, '%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮亏=%.2f, 已实现盈利=%.2f（最大持有量=%s,%.1f小时）\t%s' % (
                                self.symbol, self.side, sum(self.buy_qty)*self.avg, self.avg, sum(self.buy_qty) * (self.avg - self.present_price), self.win,
                                self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                    ## 如果仓位盈利且到达阀值后进行止盈平仓
                    ## 判断 not condition 能继续开仓且 当前最新价格 >= 购买价格 * (1 + 加减仓百分比阀值 * 下单数量的自然对数)
                    elif (not condition) and self.present_price >= self.last_sell * (1 + self.add_rate * np.log(1 - self.step)):
                        # 给本轮马丁挂上止盈, 重置重新开始下一轮
                        to_log(self.name, '{}/{} 重新开始下一轮'.format(self.symbol, self.side))
                        res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty[-2:]), price=round(self.avg*(1-0.002), self.price_precision), positionSide='SHORT')
                        res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty[:-2]), price=round(self.avg*(1-self.profit), self.price_precision), positionSide='SHORT')
                        self.step = 0
                        self.avg = 0.0
                        self.last_sell = 0.0
                        self.buy_qty = []
                        self.lowest_price = 100000.0
                        self.highest_price = 0.0
                        self.base_price = 0.0
                        self.avg_tmp = 0.0

                    # 判断 第一次开仓后 && (当前价格 小于等于 购买价格 * (1 - ))
                    elif self.step == -1 and (self.present_price <= self.avg * (1 - self.profit) or (self.present_price <= self.avg * (1 - 0.002) and self.lowest_price < 100000)):
                        self.lowest_price = min(self.present_price, self.lowest_price)
                        if self.present_price >= self.lowest_price * (1 + (1 - self.lowest_price / self.avg) / 5):
                            to_log(self.name, '{}/{} 平空'.format(self.symbol, self.side))
                            res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty), price=None, positionSide='SHORT')
                            if not 'orderId' in res_long:
                                to_log(self.name, '%s/%s 平空失败 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                continue
                            self.win += sum(self.buy_qty) * (self.avg - self.present_price) * (1-4e-4)
                            self.step = 0
                            self.avg = 0.0
                            self.last_sell = 0.0
                            self.buy_qty = []
                            self.lowest_price = 100000.0
                            self.highest_price = 0.0
                            self.base_price = 0.0
                            self.avg_tmp = 0.0
                            to_log(self.name, '%s/%s 清仓, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                        else:
                            if self.present_price <= self.base_price * (1 - self.profit):
                                if self.base_price < self.avg:
                                    self.avg = self.avg_tmp
                                self.avg_tmp = (self.avg * sum(self.buy_qty) / self.buy_qty[0] + self.present_price) / (sum(self.buy_qty) / self.buy_qty[0] + 1)
                                to_log(self.name, '{}/{} 浮盈加仓'.format(self.symbol, self.side))
                                res_short = trade.open_order(self.symbol, 'SELL', self.buy_qty[0], price=None, positionSide='SHORT')
                                if not 'orderId' in res_short:
                                    if res_short['msg'] == 'Margin is insufficient.':
                                        to_log(self.name, '%s/%s 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    else:
                                        to_log(self.name, '%s/%s 加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                                    continue

                                self.base_price *= 1 - self.profit
                                self.buy_qty.append(self.buy_qty[0])
                                self.win -= self.buy_qty[-1] * self.present_price * 4e-4
                                to_log(self.name, '%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (
                                    self.symbol, self.side, sum(self.buy_qty) * self.avg_tmp, self.avg_tmp, sum(self.buy_qty) * (self.present_price - self.avg), self.win,
                                    self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                    elif self.step < -1 and self.present_price <= self.avg * (1 - 0.003):
                        to_log(self.name, '{}/{} 平最近一次加仓'.format(self.symbol, self.side))
                        # 下单平仓
                        res_long = trade.open_order(self.symbol, 'BUY', self.buy_qty[-1], price=None, positionSide='SHORT')
                        # 判断下单平仓
                        if not 'orderId' in res_long:
                            to_log(self.name, '{}/{} 平空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                            continue
                        nums = self.buy_qty.pop()
                        self.win += nums * (self.avg - self.present_price) * (1-4e-4)
                        self.step = -1
                        self.base_price = self.avg
                        self.highest_price = 0.0
                        self.last_sell = self.avg
                        to_log(self.name, '%s/%s 剩余仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, sum(self.buy_qty)*self.avg, self.avg, sum(self.buy_qty) * (self.avg - self.present_price), self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))
                time.sleep(6)

            # 如果策略为开 多 时
            else:
                # 当起始位为 0, 则没有任何开单
                if self.step == 0:
                    # 判断当前价格 大于/等于 后三根 k 线的最大值
                    buy_condition1 = self.present_price >= max(price1m_high[-4:-1])
                    # buy_condition1 = self.present_price >= max(price1m_high[0:4])
                    # 判断当前价格 小于/等于 后四根 k 线的最小值
                    buy_condition2 = self.present_price <= min(price1m_high[-5:-1])
                    
                    # 判断是否存在
                    if buy_condition1 or buy_condition2:
                        to_log(self.name, '{}/{} 开多'.format(self.symbol, self.side))
                        # 下单开多
                        res_long = trade.open_order(self.symbol, 'BUY', self.position_size, price=None, positionSide='LONG')
                        # 判断是否下单成功
                        if not 'orderId' in res_long:
                            to_log(self.name, '{}/{} 开多失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                            time.sleep(10)
                            continue
                        self.avg = self.present_price
                        self.base_price = self.avg
                        self.sell_qty.append(self.position_size)
                        self.step += 1
                        self.last_buy = self.present_price
                        self.win -= self.position_size * self.present_price * 4e-4
                        # 开单成功后
                        to_log(self.name, '%s/%s 当前仓位成本=%.1f, 开仓价=%.3f\t%s' % (self.symbol, self.side, sum(self.sell_qty) * self.avg, self.avg, PublicModels.changeTime(time.time())))

                # 判断起始位大于 0, 至少开过一次仓
                elif self.step > 0:
                    # condition = sum(self.sell_qty)*self.present_price<self.position_times*self.free_money/2
                    # 判断当前 开单数量 是否小于 最大可开单值
                    condition = sum(self.sell_qty) / self.min_qty < self.max_add_times
                    # 判断 没有亏损 && (not 开单数量上限) && 当前价格 小于等于 最新下单价格 * (1 - 容忍爆仓率 * )
                    if self.if_loss and (not condition) and self.present_price <= self.last_buy * (1 - self.add_rate * np.log(1 + self.step)):
                        to_log(self.name, '{}/{} 平多止损'.format(self.symbol, self.side))
                        res_short = trade.open_order(self.symbol, 'SELL', sum(self.sell_qty), price=None, positionSide='LONG')
                        if not 'orderId' in res_short:
                            to_log(self.name, '%s/%s 平多失败 \t%s\t%s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                            continue
                        self.win += sum(self.sell_qty) * (self.present_price - self.avg) * (1-4e-4)
                        self.step = 0
                        self.avg = 0.0
                        self.last_buy = 0.0
                        self.sell_qty = []
                        self.lowest_price = 100000.0
                        self.highest_price = 0.0
                        self.base_price = 0.0
                        self.avg_tmp = 0.0

                    elif condition and self.present_price <= self.last_buy * (1 - self.add_rate * np.log(1 + self.step)):
                        self.lowest_price = min(self.present_price, self.lowest_price)
                        if self.present_price >= self.lowest_price * (1 + (1 - self.lowest_price / self.last_buy) / 5):
                            to_log(self.name, '{}/{} 加仓'.format(self.symbol, self.side))
                            res_long = trade.open_order(self.symbol, 'BUY', sum(self.sell_qty), price=None, positionSide='LONG')
                            if not 'orderId' in res_long:
                                if res_long['msg'] == 'Margin is insufficient.':
                                    to_log(self.name, '%s/%s 可用金不足 \t%s\t%s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                else:
                                    to_log(self.name, '%s/%s 加仓失败 \t%s\t%s'%(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                continue
                            self.avg = (self.avg + self.present_price) / 2
                            self.last_buy = self.present_price
                            self.sell_qty.append(sum(self.sell_qty))
                            self.step += 1
                            self.win -= self.sell_qty[-1] * self.present_price * 4e-4
                            to_log(self.name, '%s/%s 当前仓位成本=%.1f, 均价=%.3f, 浮亏=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, sum(self.sell_qty) * self.avg, self.avg,
                                    sum(self.sell_qty) * (self.present_price - self.avg), self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                    elif (not condition) and self.present_price <= self.last_buy * (1 - self.add_rate * np.log(1 + self.step)):
                        to_log(self.name, '{}/{} 重新开始下一轮'.format(self.symbol, self.side))
                        trade.open_order(self.symbol, 'SELL', sum(self.sell_qty[-2:]), price=round(self.avg*(1+0.002),self.price_precision), positionSide='LONG')
                        trade.open_order(self.symbol, 'SELL', sum(self.sell_qty[:-2]), price=round(self.avg*(1+self.profit),self.price_precision), positionSide='LONG')
                        self.step = 0
                        self.avg = 0.0
                        self.last_buy = 0.0
                        self.sell_qty = []
                        self.lowest_price = 100000.0
                        self.highest_price = 0.0
                        self.base_price = 0.0
                        self.avg_tmp = 0.0

                    elif self.step == 1 and (self.present_price >= self.avg * (1 + self.profit) or (self.present_price >= self.avg * (1 + 0.002) and self.highest_price > 0)):
                        self.highest_price = max(self.present_price, self.highest_price)
                        # 最高处回调达到止盈位置则清仓
                        if self.present_price <= self.highest_price * (1 - (self.highest_price / self.avg - 1) / 5):  # 重仓情形考虑回本平一半或平xx%的仓位, 待计算, 剩下依然重仓考虑吃多少点清仓
                            to_log(self.name, '{}/{} 平多'.format(self.symbol, self.side))
                            res_short = trade.open_order(self.symbol, 'SELL', sum(self.sell_qty), price=None, positionSide='LONG')
                            if not 'orderId' in res_short:
                                to_log(self.name, '%s/%s 平多失败\t%s\t%s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
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
                            to_log(self.name, '%s/%s 清仓, 已实现盈利=%.2f（最大持有量=%s,%.1f小时）\t%s' % (self.symbol, self.side, self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                        else:
                            if self.present_price >= self.base_price * (1 + self.profit):
                                if self.base_price > self.avg:
                                    self.avg = self.avg_tmp
                                self.avg_tmp = (self.avg * sum(self.sell_qty) / self.sell_qty[0] + self.present_price) / (sum(self.sell_qty) / self.sell_qty[0] + 1)
                                to_log(self.name, '{}/{} 浮盈加仓'.format(self.symbol, self.side))
                                res_long = trade.open_order(self.symbol, 'BUY', self.sell_qty[0], price=None, positionSide='LONG')
                                if not 'orderId' in res_long:
                                    if res_long['msg'] == 'Margin is insufficient.':
                                        to_log(self.name, '%s/%s 可用金不足 \t %s \t %s' % (self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    else:
                                        to_log(self.name, '%s/%s 加仓失败 \t %s \t %s'%(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                                    continue
                                self.base_price *= 1 + self.profit
                                self.sell_qty.append(self.sell_qty[0])
                                self.win -= self.sell_qty[-1] * self.present_price * 4e-4

                    elif self.step > 1 and self.present_price >= self.avg * (1 + 0.003):
                        to_log(self.name, '{}/{} 平最近一次加仓'.format(self.symbol, self.side))
                        res_short = trade.open_order(self.symbol, 'SELL', self.sell_qty[-1], price=None, positionSide='LONG')
                        if not 'orderId' in res_short:
                            to_log(self.name, '%s/%s 平多失败 \t %s \t %s' % (self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                            continue
                        nums = self.sell_qty.pop()
                        self.win += nums * (self.present_price - self.avg) * (1-4e-4)
                        self.step = 1
                        self.lowest_price = 100000.0
                        self.base_price = self.avg
                        self.last_buy = self.avg
                        to_log(self.name, '%s/%s 剩余仓位成本=%.1f, 均价=%.3f, 浮盈=%.2f, 已实现盈利=%.2f（最大持有量=%s, %.1f小时）\t %s' % (self.symbol, self.side, sum(self.sell_qty)*self.avg, self.avg, sum(self.sell_qty) * (self.present_price - self.avg), self.win, self.max_position, (time.time() - self.t_start) / 3600, PublicModels.changeTime(time.time())))

                # time.sleep(max(2,self.rule['rateLimits'][0]['limit'] // 600))
                time.sleep(6)
            self.max_position = max(self.max_position, sum(self.buy_qty), sum(self.sell_qty)) / self.min_qty

if __name__ == '__main__':
    args = command_line_args(sys.argv[1:])
    conn_setting = {'symbol': args.symbol, 'key': args.key, 'secret': args.secret}
    gs = GridStrategy(**conn_setting)
    gs.grid_run()