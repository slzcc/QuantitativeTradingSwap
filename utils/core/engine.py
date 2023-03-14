#***********************************************
#
#      Filename: engine.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 下单引擎
#
#        Create: 2022-12-08 14:36:02
# Last Modified: 2022-12-08 14:36:02
#
#***********************************************
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import math
import statsmodels.api as sm
import talib
import pandas_ta as ta
import time
from utils.method import redisMethod


def DirectionVolatilityFaultTolerance(token, symbol):
    """
    方向波动容错 下单入口
    """
    redisClient = redisMethod.redisUtils()

    klines = redisClient.getKey("{}_futures_{}_kline".format(token, symbol))
    _PrivateDataFrameEMA(json.loads(klines))
    _PrivateDataFrameMA(json.loads(klines))

def x():
    """
    判断是否平仓
    """
    pass

def new_match(match_result):
    # 判断当前差异线时间点是否在当前可开单范围内
    for match in match_result:
        if (match[2] / 1000 - time.time()) >= 0:
            return match

def _PrivateDataFrameEMA(klines):

    if klines:
        price_kline = klines
        price_close = list(map(lambda x: float(x[4]), price_kline))
        timestamp_close = list(map(lambda x: float(x[6]), price_kline))

        data = pd.DataFrame()
        data["PriceClose"] = pd.DataFrame(price_close)
        timestamp_close_tmp = []
        for i in timestamp_close:
            timestamp_close_tmp.append(Decimal(i))
        data.insert(loc=1, column='Timestamp',value=timestamp_close_tmp)

        data['EMA_Min'] = ta.ema(data['PriceClose'], length=7)
        data['EMA_Max'] = ta.ema(data['PriceClose'], length=20)
        data['Position'] = np.where(data['EMA_Min'] > data['EMA_Max'], 0, -1)
        data.dropna(inplace=True)

        data_p_len = len(data['Position'])
        data_dropna_len = data['Position'].index[0]

        match_result = []
        for index, item in enumerate(data['Position']):
            if index == 0:
                pass
            elif (data_p_len - 1) >= index:
                if data['Position'][index + data_dropna_len] != data['Position'][index + data_dropna_len - 1]:
                    match_result.append([data['PriceClose'][index + data_dropna_len], item, int(data["Timestamp"][index + data_dropna_len])])

        # 当 Max 大于 Min 上升趋势 -1
        # 当 Min 大于 Max 下降趋势 0
        res = new_match(match_result)
        if res:
            if res[1]:
                # 等于 -1
                return (res[0], 'LONG')
            else:
                # 等于 0
                return (res[0], 'SHORT')

def _PrivateDataFrameMA(klines):

    if klines:
        price_kline = klines
        price_close = list(map(lambda x: float(x[4]), price_kline))
        timestamp_close = list(map(lambda x: float(x[6]), price_kline))
        price_array = np.asarray(price_close)

        MA_Min = talib.MA(price_array, 7)
        MA_Max = talib.MA(price_array, 20)

        data = pd.DataFrame()
        data["PriceClose"] = pd.DataFrame(price_close)
        timestamp_close_tmp = []
        for i in timestamp_close:
            timestamp_close_tmp.append(Decimal(i))
        data.insert(loc=1, column='Timestamp',value=timestamp_close_tmp)

        data['MA_Min'] = pd.DataFrame(MA_Min)
        data['MA_Max'] = pd.DataFrame(MA_Max)
        data['Position'] = np.where(data['MA_Min'] > data['MA_Max'], 0, -1)
        data.dropna(inplace=True)

        data_p_len = len(data['Position'])
        data_dropna_len = data['Position'].index[0]

        match_result = []
        for index, item in enumerate(data['Position']):
            if index == 0:
                pass
            elif (data_p_len - 1) >= index:
                if data['Position'][index + data_dropna_len] != data['Position'][index + data_dropna_len - 1]:
                    match_result.append([data['PriceClose'][index + data_dropna_len], item, int(data["Timestamp"][index + data_dropna_len])])

        # 当 Max 大于 Min 上升趋势 -1
        # 当 Min 大于 Max 下降趋势 0
        res = new_match(match_result)
        if res:
            if res[1]:
                # 等于 -1
                return (res[0], 'LONG')
            else:
                # 等于 0
                return (res[0], 'SHORT')

def _PrivateDataFrameEMA2(klines):

    if klines:
        price_kline = klines
        price_close = list(map(lambda x: float(x[4]), price_kline))
        timestamp_close = list(map(lambda x: float(x[6]), price_kline))
        price_array = np.asarray(price_close)

        Min = talib.EMA(price_array, 5)
        Max = talib.EMA(price_array, 10)

        data = pd.DataFrame()
        data["PriceClose"] = pd.DataFrame(price_close)
        timestamp_close_tmp = []
        for i in timestamp_close:
            timestamp_close_tmp.append(Decimal(i))
        data.insert(loc=1, column='Timestamp',value=timestamp_close_tmp)

        data['Min'] = pd.DataFrame(Min)
        data['Max'] = pd.DataFrame(Max)
        data['Position'] = np.where(data['Min'] > data['Max'], 0, -1)
        data.dropna(inplace=True)

        data_p_len = len(data['Position'])
        data_dropna_len = data['Position'].index[0]

        match_result = []
        for index, item in enumerate(data['Position']):
            if index == 0:
                pass
            elif (data_p_len - 1) >= index:
                if data['Position'][index + data_dropna_len] != data['Position'][index + data_dropna_len - 1]:
                    match_result.append([data['PriceClose'][index + data_dropna_len], item, int(data["Timestamp"][index + data_dropna_len])])

        # 当 Max 大于 Min 上升趋势 -1
        # 当 Min 大于 Max 下降趋势 0
        res = new_match(match_result)
        if res:
            if res[1]:
                # 等于 -1
                return (res[0], 'LONG')
            else:
                # 等于 0
                return (res[0], 'SHORT')
