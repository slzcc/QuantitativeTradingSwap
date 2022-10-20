#***********************************************
#
#      Filename: getkilneData.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 通过 Binance API 获取 K 线数据
#
#        Create: 2022-10-08 14:58:33
# Last Modified: 2022-10-08 14:58:33
#
#***********************************************

import requests
from conf.settings import *
from utils import public as PublicModels

def get_present_price(coin):
    # 最新价
    url = '{}/fapi/v1/ticker/price?symbol={}'.format(FUTURE_URL, coin)
    return PublicModels.PublicRequests(request={"model": "GET", "url": url, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

def get_history_k(coin, typ, T='4h', limit=1000, start_time=None, end_time=None):
    # 历史k线
    '''
    :param coin: 币种
    :param typ: 类型（现货/合约）
    :param T: 时间级别
    :return: 直接返回接口完整历史k线数据，默认1000条
    '''
    if typ == 'spot':
        url = '{}/api/v1/klines?symbol={}&interval={}&limit={}'.format(SPOT_URL, coin, T,limit)
        return PublicModels.PublicRequests(request={"model": "GET", "url": url, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})
    else:
        if start_time and end_time:
            url = '{}/fapi/v1/klines?symbol={}&interval={}&startTime={}&endTime={}'.format(FUTURE_URL, coin, T, start_time, end_time)
            return PublicModels.PublicRequests(request={"model": "GET", "url": url, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})
        else:
            url = '{}/fapi/v1/klines?symbol={}&interval={}&limit={}'.format(FUTURE_URL, coin, T, limit)
            return PublicModels.PublicRequests(request={"model": "GET", "url": url, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

def get_24hr():
    # 24小时U本位数据
    try:
        res = PublicModels.PublicRequests(request={"model": "GET", "url": '{}/fapi/v1/ticker/24hr'.format(FUTURE_URL), "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10}).json()
    except:
        res = {}
    return sorted([[i["symbol"],float(i["quoteVolume"]),float(i["lastPrice"]),i["volume"]] for i in res], key=lambda x:x[1], reverse=True)

def long_short_ratio(coin,T):
    # 多空人数比，"5m","15m","30m","1h","2h","4h","6h","12h","1d"
    try:
        res = PublicModels.PublicRequests(request={"model": "GET", "url": '{}/futures/data/globalLongShortAccountRatio?symbol={}&period={}&limit=500'.format(FUTURE_URL, coin, T), "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10}).json()
    except:
        res = {}
    return [float(i['longShortRatio']) for i in res]

def top_long_short_ratio(coin,T):
    # 大户持仓量多空比
    try:
        res = PublicModels.PublicRequests(request={"model": "GET", "url": '{}/futures/data/topLongShortPositionRatio?symbol={}&period={}&limit=500'.format(FUTURE_URL, coin, T), "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10}).json()
    except:
        res = {}
    return [float(i['longShortRatio']) for i in res]

def take_long_short_ratio(coin,T):
    # 主动买卖量比
    url='{}/futures/data/takerlongshortRatio?symbol={}&period={}&limit=500'.format(FUTURE_URL, coin, T)
    return PublicModels.PublicRequests(request={"model": "GET", "url": url, "timeout": 5, "verify": True, "proxies": PROXIES_DEFAULT_DATA}, recursive_abnormal={"recursive": 10, "count": 0, "alert_count": 10})

