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
        # 获取一个 Binance API 对象
        trade = tradeAPI.TradeApi(self.key, self.secret)
        # 更改持仓方式，默认单向
        checkAccount = trade.change_side(False)
        if "code" in checkAccount.keys():
            if checkAccount["code"] != -4059:
                raise AssertionError("账户凭证存在异常, 返回内容 {}, 请检查后继续!".format(checkAccount))

        # 变换逐全仓, 默认逐仓
        trade.change_margintype(self.symbol, isolated=False)
        # 调整开仓杠杆
        trade.set_leverage(self.symbol, self.position_times)
        # 设置当前启动时间
        t_start = time.time()
        to_log(self.name, '{}/{} U本位开始运行 \t {} \t #################'.format(self.symbol, self.side, PublicModels.changeTime(time.time())))
        while True:
            # 获取 1m 时间的 k 线
            klines = get_history_k(typ='futures', coin=self.symbol, T='1m')
            # 获取 k 线中最低的价格(取每个 list 中第 3 个位置数据)
            price1m_low = list(map(lambda x: float(x[3]), klines))
            # 获取 k 线中最高的价格(取每个 list 中第 2 个位置数据)
            price1m_high = list(map(lambda x: float(x[2]), klines))
            # 获取 k 线中现在的价格
            self.present_price = float(klines[-1][4])
            # 记录最小购买单价
            self.position_size = self.min_qty
            # 如果策略为开 空 时
            if self.side != '多':
                to_log(self.name, '{}/{} U本位合约正在运行, 当前价格 {} , 已购买币种总数 {} , 已经下单总次数 {} , 锚点位置 {} \t {}'.format(
                    self.symbol, self.side, self.present_price, sum(self.buy_qty), len(self.buy_qty), self.step, PublicModels.changeTime(time.time())))
                # 起始位置 0, 且没有开仓
                if self.step == 0:
                    # 判断当前价格 小于/等于 后三根 k 线的最小值
                    sell_condition1 = self.present_price <= min(price1m_low[-4:-1])
                    # 判断当前价格 大于/等于 前四根 k 线的最大值
                    sell_condition2 = self.present_price >= max(price1m_high[:5])

                    # 判断数据是否为空
                    if sell_condition1 or sell_condition2:
                        to_log(self.name, '{}/{} 下单开空'.format(self.symbol, self.side))
                        # 下单开空, 市价开单
                        res_short = trade.open_order(self.symbol, 'SELL', self.position_size, price=None, positionSide='SHORT')
                        # 判断下单是否成功
                        if not 'orderId' in res_short:
                            to_log(self.name, '{}/{} 开空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_short), PublicModels.changeTime(time.time())))
                            time.sleep(3)
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
                        to_log(self.name, '%s/%s 当前仓位成本=%.1f, 开仓价=%.3f\t%s' % (self.symbol, self.side, sum(self.buy_qty) * self.avg, self.avg, PublicModels.changeTime(time.time())))

                # 当锚点为负数时, 证明已下过单
                elif self.step < 0:
                    # 判断是否可以继续下单，返回布尔值
                    # 开仓总币价 / 每单币价 < 开仓数量
                    condition = sum(self.buy_qty) / self.min_qty < self.max_add_times
                    # 判断 仓位 是否需要进行止损(全仓平仓)
                    ## 判断 亏损 && (是否可以继续开仓) && 当前价格 大于等于 准备出售价格 乘以 (1 + 1.2 * 开仓数量比例值) ep: 19700.0 * (1 + 1.2 * np.log(1 - -1))
                    ## 主要判断亏损如果超过范围则进行止损平仓（开仓数量到达上限）
                    if self.if_loss and (not condition) and self.present_price >= self.last_sell * (1 + self.add_rate * np.log(1 - self.step)):
                        to_log(self.name, '{}/{} 平空止损'.format(self.symbol, self.side))
                        # 下单平空(市价平所有仓位)
                        res_long = trade.open_order(self.symbol, 'BUY', sum(self.buy_qty), price=None, positionSide='SHORT')
                        # 判断下单平空
                        if not 'orderId' in res_long:
                            to_log(self.name, '{}/{} 平空失败 \t {} \t {}'.format(self.symbol, self.side, str(res_long), PublicModels.changeTime(time.time())))
                            continue
