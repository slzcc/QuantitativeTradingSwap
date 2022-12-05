#***********************************************
#
#      Filename: tradeAPI.py
#
#        Author: shilei@hotstone.com.cn
#   Description: Binance API 初始对象
#
#        Create: 2022-10-08 14:58:33
# Last Modified: 2022-10-08 14:58:33
#
#***********************************************

import requests
import time
import json
import hmac
import hashlib
from urllib.parse import urlencode
from conf.settings import binance_recvWindow, FUTURE_URL, PROXIES_DEFAULT_DATA
from utils import public as PublicModels

class TradeApi:
    def __init__(self, key, secret):
        self.api = key
        self.secret = secret

    def change_side(self, one_side=True):
        '''更改持仓模式，默认单向'''
        path = "{}/fapi/v1/positionSide/dual".format(FUTURE_URL)
        params = {'dualSidePosition': 'false' if one_side else 'true', 'recvWindow': binance_recvWindow}
        query = self._sign(self.secret, params)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "POST", "url": path, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def change_margintype(self, symbol, isolated=True):
        '''变换逐全仓，默认逐仓'''
        path = "{}/fapi/v1/marginType".format(FUTURE_URL)
        params = {'symbol': symbol, 'marginType': 'ISOLATED' if isolated else 'CROSSED', 'recvWindow': binance_recvWindow}
        query = self._sign(self.secret, params)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "POST", "url": path, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def set_leverage(self, symbol, leverage):
        ''' 调整开仓杠杆'''
        path = "{}/fapi/v1/leverage".format(FUTURE_URL)
        params = {'symbol': symbol, 'leverage': leverage, 'recvWindow': binance_recvWindow}
        query = self._sign(self.secret, params)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "POST", "url": path, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def get_balance(self):
        '''账户余额'''
        path = "{}/fapi/v2/balance".format(FUTURE_URL)
        params = {"recvWindow": binance_recvWindow}
        query = urlencode(self._sign(self.secret, params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "GET", "url": url, "header": header, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def get_account(self):
        '''账户信息'''
        path = "{}/fapi/v2/account".format(FUTURE_URL)
        params = {"recvWindow": binance_recvWindow}
        query = urlencode(self._sign(self.secret, params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "GET", "url": url, "header": header, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

        try:
            position_list = list(filter(lambda x: x['initialMargin'] != '0', res['positions']))
            return res['totalWalletBalance'], res['availableBalance'], position_list
        except:
            print(res)
            return '','', []

    def get_income(self, timestamp=None):
        '''账户损益资金流水'''
        if timestamp:
            path = "{}/fapi/v1/income?startTime={}&endTime={}".format(FUTURE_URL, timestamp[0], timestamp[1])
        else:
            path = "{}/fapi/v1/income".format(FUTURE_URL)
        params = {"recvWindow": binance_recvWindow}
        query = urlencode(self._sign(self.secret, params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "GET", "url": url, "header": header, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def get_positionrisk(self):
        '''用户持仓风险
        [
            {
                "entryPrice": "0.00000", // 开仓均价
                "marginType": "isolated", // 逐仓模式或全仓模式
                "isAutoAddMargin": "false",
                "isolatedMargin": "0.00000000", // 逐仓保证金
                "leverage": "10", // 当前杠杆倍数
                "liquidationPrice": "0", // 参考强平价格
                "markPrice": "6679.50671178",   // 当前标记价格
                "maxNotionalValue": "20000000", // 当前杠杆倍数允许的名义价值上限
                "positionAmt": "0.000", // 头寸数量，符号代表多空方向, 正数为多，负数为空
                "symbol": "BTCUSDT", // 交易对
                "unRealizedProfit": "0.00000000", // 持仓未实现盈亏
                "positionSide": "BOTH", // 持仓方向
                "updateTime": 1625474304765   // 更新时间
            }
        ]
        '''
        path = "{}/fapi/v2/positionRisk".format(FUTURE_URL)
        try:
            params = {"recvWindow": binance_recvWindow}
            query = urlencode(self._sign(self.secret, params))
            url = "%s?%s" % (path, query)
            header = {"X-MBX-APIKEY": self.api}
            return list(filter(lambda x:float(x['entryPrice']) > 0, PublicModels.PublicRequests(request={"model": "GET", "url": url, "header": header, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})))

        except Exception as e:
            print(e)
            return []

    def get_history_order(self, symbol=None, start=None, end=None):
        '''成交历史'''
        path = "{}/fapi/v1/userTrades".format(FUTURE_URL)
        params = {"recvWindow": binance_recvWindow}
        params["symbol"] = symbol if symbol else ""
        if start and end:
            params["start"] = start
            params["end"] = end
        query = urlencode(self._sign(self.secret, params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "GET", "url": url, "header": header, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def open_order(self, symbol, side, quantity, price, positionSide, timesleep=1):
        ''' 开单(U本位)
            :param side: BUY SELL
        '''
        path = "{}/fapi/v1/order".format(FUTURE_URL)
        params = self._order(symbol, quantity, side, price, positionSide)
        params["recvWindow"] = binance_recvWindow
        query = self._sign(self.secret, params)
        header = {"X-MBX-APIKEY": self.api}
        time.sleep(timesleep)
        return PublicModels.PublicRequests(request={"model": "POST", "url": path, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def open_order_b(self, symbol, side, quantity, price, positionSide, timesleep=1):
        ''' 开单(币本位)
            :param side: BUY SELL
        '''
        path = "{}/bapi/v1/order".format(FUTURE_URL)
        params = self._order(symbol, quantity, side, price, positionSide)
        params["recvWindow"] = binance_recvWindow
        query = self._sign(self.secret, params)
        header = {"X-MBX-APIKEY": self.api}
        time.sleep(timesleep)
        return PublicModels.PublicRequests(request={"model": "POST", "url": path, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def order_reduce(self, symbol, side, positionSide, tp, quantity=None, price=None, stopPrice=None, callbackRate=1.0, activationPrice=None):
        # 止盈止损挂单
        # tp:STOP/TAKE_PROFIT/STOP_MARKET/TAKE_PROFIT_MARKET/TRAILING_STOP_MARKET
        # 跟踪回调范围[0.1,5]，百分比
        path = "{}/fapi/v1/order".format(FUTURE_URL)
        params = {
            "symbol": symbol,
            "side": side,
            "positionSide": positionSide,
            "type": tp,
            "recvWindow": binance_recvWindow
        }
        if tp in ['STOP', 'TAKE_PROFIT']:
            params["quantity"] = quantity
            params["price"] = price
            params["stopPrice"] = stopPrice
        elif tp in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
            params["stopPrice"] = stopPrice
            params["closePosition"] = True
        elif tp == 'TRAILING_STOP_MARKET':
            params["callbackRate"] = callbackRate
            params["activationPrice"] = activationPrice
            params["quantity"] = quantity
        query = self._sign(self.secret, params)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "POST", "url": path, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def check_order(self, symbol, orderId):
        '''查询订单'''
        path = "{}/fapi/v1/order".format(FUTURE_URL)
        params = {"symbol": symbol, "orderId": orderId, "recvWindow": binance_recvWindow}
        query = urlencode(self._sign(self.secret, params))
        url = "%s?%s" % (path, query)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "GET", "url": url, "header": header, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def cancel_one_order(self, symbol, orderId):
        '''撤销某订单'''
        path = "{}/fapi/v1/order".format(FUTURE_URL)
        params = {"symbol": symbol,"orderId": orderId}
        params.update({"recvWindow": binance_recvWindow})
        query = self._sign(self.secret, params)
        url = "%s" % (path)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "DELETE", "url": url, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def cancel_orders(self,symbol):
        '''撤销全部订单'''
        path = "{}/fapi/v1/allOpenOrders".format(FUTURE_URL)
        params = {"symbol": symbol}
        params.update({"recvWindow": binance_recvWindow})
        query = self._sign(self.secret, params)
        url = "%s" % (path)
        header = {"X-MBX-APIKEY": self.api}
        return PublicModels.PublicRequests(request={"model": "DELETE", "url": url, "header": header, "params": query, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

    def _order(self, symbol, quantity, side, price, positionSide):
        params = {}
        if price is not None:
            params["type"] = "LIMIT"
            params["price"] = '%.8f' % price
            params["timeInForce"] = "GTC"
        else:
            params["type"] = "MARKET"
        params["symbol"] = symbol
        params["side"] = side
        # if not closePosition:
        #     params["quantity"] = '%.8f' % quantity
        # else:
        #     params["closePosition"] = True
        #     params["type"] = "STOP_MARKET"
        #     params["stopPrice"] = price
        #     del params["price"]
        params["quantity"] = '%.8f' % quantity
        params["positionSide"] = positionSide
        return params

    def _sign(self, secret="", params={}):
        '''获取认证 Token'''
        data = params.copy()
        ts = int(1000 * time.time())
        data.update({"timestamp": ts})
        h = urlencode(data)
        b = bytearray()
        b.extend(secret.encode())
        signature = hmac.new(b, msg=h.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()
        data.update({"signature": signature})
        return data

