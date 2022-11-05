#***********************************************
#
#      Filename: toolsMethod.py
#
#        Author: shilei@hotstone.com.cn
#   Description: tools 方法
#
#        Create: 2022-10-26 16:30:32
# Last Modified: 2022-10-26 16:30:32
#
#***********************************************
from decimal import Decimal
from utils.method import redisMethod
from utils.binance import tradeAPI
from logging.handlers import TimedRotatingFileHandler

import os
import time
import logging
import json

def checkListDetermine(llist, determine, count=0, setp=0, length=1):
    """
    获取 列表 中的参数值是否可以得到 determine 的值

    :param   llist       # 传入一个列表 (不区分 float 或 or)
    :param   determine   # 判断值, 在列表中获取与此值相等的索引位
    :return  (False/True, [])
    """
    if len(llist) != 1 and len(llist) == length:
        return False, [], []
    if len(llist) -1 < setp:
        setp = 0
        length += 1
    if count == 0:
        _checkType = False
        for index, item in enumerate(llist):
            if item == determine:
                return True, [index], [item]
        if not _checkType:
            return checkListDetermine(llist, determine, count=count + 1)
    else:
        _checkType = False
        _number = 0.0
        _index = []
        _item = []
        for index, item in enumerate(llist[setp::length]):
            _number = Decimal(str(item)) + Decimal(str(_number))
            _index.append(index + setp + length)
            _item.append(item)
            if _number == Decimal(str(determine)):
                return True, _index, _item
        if not _checkType:
            return checkListDetermine(llist, determine, count=count, setp=setp + 1, length=length)

def checkRedisKeyValues(redisClient, token, direction, condition=None):
    # 输出 Redis 数据内容
    _env = {}
    for item in redisClient.getKeys("{}*{}".format(token, direction)):
        _env[item] = redisClient.getKey(item)
    for item in redisClient.getKeys("{}*qty".format(token)):
        _env[item] = redisClient.lrangeKey(item, 0, -1)
    _env["condition"] = condition
    return _env

def longOrderUndo(trade, logger, symbol, token, direction, orderInfo, timestamp=1800, rate=0.007, checkIDdelayNumber=7):
    """
    :trade  tradeObject
    :param  logger/Object:          日志对象
    :param  symbol/string:          币对
    :param  token/string:           任务 Token
    :param  direction/string:       合约方向
    :param  orderInfo/dict:         订单数据
    :param  timestamp/int:          订单超时时间
    :param  rate/float:             订单价格超出百分比后进行撤单
    :param  checkIDdelayNumber/int  订单延迟次数, 当一个订单被检测到一定数量后才会被撤单
    处理长期没有通过的委托单
    timestamp
    判断委托单时间超过 30 分钟并且下单价格与现价差距过大时 进行撤单
    """

    redisClient = redisMethod.redisUtils()

    orderOfTime = orderInfo["updateTime"] / 1000

    logger.info("正在检测委托单是否失效 {}".format(orderInfo))

    if (time.time() - orderOfTime) >= timestamp:
        # 当方向是 开多 时且是买单时
        if orderInfo["side"] == "BUY" and direction == "LONG":
            # 现价大于开单价则需要进行撤单并恢复下单池可以数量
            if float(redisClient.getKey("{}_present_price_{}".format(token, direction))) / float(orderInfo["price"]) >= 1 + rate:
                # 更新 redis 下单池
                for index, item in enumerate([float(item) for item in redisClient.lrangeKey("{}_long_qty".format(token), 0, -1)]):
                    if item == float(orderInfo["origQty"]):
                        if not redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction)):
                            # 设置这个 key 7 天过期
                            redisClient.setKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction), 1, expire=10080)
                        elif int(redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))) == checkIDdelayNumber:
                            redisClient.lremKey("{}_long_qty".format(token), index, item)
                            logger.info("委托单 {} 已经撤单, 并恢复下单池".format(orderInfo))
                            redisClient.delKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
                            # 撤销委托单
                            res = trade.cancel_one_order(symbol, orderInfo["orderId"])
                            return True
                        else:
                            redisClient.incrKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
        # 当方向是 开多 时且是卖单时
        elif orderInfo["side"] == "SELL" and direction == "LONG":
            # 现价小于开单价则需要进行撤单并恢复下单池可以数量
            if float(redisClient.getKey("{}_present_price_{}".format(token, direction))) / float(orderInfo["price"]) <= 1 - rate:
                # 更新 redis 下单池
                for index, item in enumerate([float(item) for item in redisClient.lrangeKey("{}_long_qty".format(token), 0, -1)]):
                    if item == float(orderInfo["origQty"]):
                        if not redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction)):
                            # 设置这个 key 7 天过期 
                            redisClient.setKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction), 1, expire=10080)
                        elif int(redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))) == checkIDdelayNumber:
                            redisClient.lremKey("{}_long_qty".format(token), index, item)
                            logger.info("委托单 {} 已经撤单, 并恢复下单池".format(orderInfo))
                            redisClient.delKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
                            # 撤销委托单
                            res = trade.cancel_one_order(symbol, orderInfo["orderId"])
                            return True
                        else:
                            redisClient.incrKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
        # 当方向是 空多 时且是卖单时
        if orderInfo["side"] == "BUY" and direction == "SHORT":
            # 现价大于开单价则需要进行撤单并恢复下单池可以数量
            if float(redisClient.getKey("{}_present_price_{}".format(token, direction))) / float(orderInfo["price"]) <= 1 - rate:
                # 更新 redis 下单池
                for index, item in enumerate([float(item) for item in redisClient.lrangeKey("{}_short_qty".format(token), 0, -1)]):
                    if item == float(orderInfo["origQty"]):
                        if not redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction)):
                            # 设置这个 key 7 天过期
                            redisClient.setKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction), 1, expire=10080)
                        elif int(redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))) == checkIDdelayNumber:
                            redisClient.lremKey("{}_short_qty".format(token), index, item)
                            logger.info("委托单 {} 已经撤单, 并恢复下单池".format(orderInfo))
                            redisClient.delKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
                            # 撤销委托单
                            res = trade.cancel_one_order(symbol, orderInfo["orderId"])
                            return True
                        else:
                            redisClient.incrKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
        # 当方向是 空多 时且是买单时
        elif orderInfo["side"] == "SELL" and direction == "SHORT":
            # 现价小于开单价则需要进行撤单并恢复下单池可以数量
            if float(redisClient.getKey("{}_present_price_{}".format(token, direction))) / float(orderInfo["price"]) >= 1 + rate:                # 撤销委托单
                # 更新 redis 下单池
                for index, item in enumerate([float(item) for item in redisClient.lrangeKey("{}_short_qty".format(token), 0, -1)]):
                    if item == float(orderInfo["origQty"]):
                        if not redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction)):
                            # 设置这个 key 7 天过期
                            redisClient.setKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction), 1, expire=10080)
                        elif int(redisClient.getKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))) == checkIDdelayNumber:
                            redisClient.lremKey("{}_short_qty".format(token), index, item)
                            logger.info("委托单 {} 已经撤单, 并恢复下单池".format(orderInfo))
                            redisClient.delKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
                            # 撤销委托单
                            res = trade.cancel_one_order(symbol, orderInfo["orderId"])
                            return True
                        else:
                            redisClient.incrKey("{}_orderCheckId_{}_delay_destruction_{}".format(token, orderInfo["orderId"], direction))
        return False

def globalSetOrderIDStatus(symbol, key, secret, token):
    """
    循环 Redis key 数据
    且访问 API 判定是否成功建仓
    如果已经成功建仓则删除 key
    """
    
    redisClient = redisMethod.redisUtils()
    # 获取一个 Binance API 对象
    trade = tradeAPI.TradeApi(key, secret)
    direction = "LONG" if symbol[-1] == "多" else "SHORT"

    # 创建日志器对象
    ######################################## Logging __name__ #######################################
    logger = logging.getLogger("CheckOrders")

    # 设置logger可输出日志级别范围
    logger.setLevel(logging.DEBUG)

    # 添加控制台handler，用于输出日志到控制台
    console_handler = logging.StreamHandler()
    # 日志输出到系统
    # console_handler = logging.StreamHandler(stream=None）
    # 添加日志文件handler，用于输出日志到文件中
    #file_handler = logging.FileHandler(filename='logs/{}.log'.format(name), encoding='UTF-8', when='H', interval=6, backupCount=4)
    file_handler = TimedRotatingFileHandler(filename='logs/{}.log'.format("CheckOrders"), encoding='UTF-8', when='H', interval=6, backupCount=4)

    # 将handler添加到日志器中
    #logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # 设置格式并赋予handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    while True:
        try:
            # 获取所有 key 列表
            keyList = redisClient.getKeys("{}_orderId_*_{}_*".format(token, direction))

            for keyName in keyList:
                keyValue = json.loads(redisClient.getKey(keyName))

                orderInfo = trade.check_order(keyValue["symbol"], keyValue["orderId"]).json()
                """
                {'orderId': 3239941893,
                 'symbol': 'BTCUSDT',
                 'status': 'NEW',
                 'clientOrderId': 'hfJmdLykJCumI7CatZYnv4',
                 'price': '19988',
                 'avgPrice': '0.00000',
                 'origQty': '0.006',
                 'executedQty': '0',
                 'cumQty': '0',
                 'cumQuote': '0',
                 'timeInForce': 'GTC',
                 'type': 'LIMIT',
                 'reduceOnly': True,
                 'closePosition': False,
                 'side': 'BUY',
                 'positionSide': 'SHORT',
                 'stopPrice': '0',
                 'workingType': 'CONTRACT_PRICE',
                 'priceProtect': False,
                 'origType': 'LIMIT',
                 'updateTime': 1666170610732}
                """
                # 判断是否成功获取订单信息
                if not "updateTime" in orderInfo.keys():
                    continue

                # 判断当前委托单是否超时且已经与现在价格产生误差
                if longOrderUndo(trade, logger, keyValue["symbol"], token, direction, orderInfo, timestamp=1800, rate=0.012):
                    continue

                # 判断远程 API 当前 orderID 的状态 FILLED 为已经成功建仓 NEW 为委托单 EXPIRED 过期 CANCELED 取消订单
                if orderInfo["status"] == "FILLED":

                    # 判断是否为买多
                    if orderInfo["side"] == "BUY" and direction == "LONG" and direction == orderInfo["positionSide"]:
                        redisClient.lpushKey("{}_real_long_qty".format(token), orderInfo["origQty"])
                        logger.info("订单方向 {} 信息 {} 成功 建仓 并录入到 {} 数量 {} 当前值 {}".format(direction, orderInfo, "{}_real_long_qty".format(token), orderInfo["origQty"], [float(item) for item in redisClient.lrangeKey("{}_real_long_qty".format(token), 0, -1)]))
                        redisClient.delKey(keyName)
                    # 判断是否为买空
                    elif orderInfo["side"] == "SELL" and direction == "SHORT" and direction == orderInfo["positionSide"]:
                        redisClient.lpushKey("{}_real_short_qty".format(token), orderInfo["origQty"])
                        logger.info("订单方向 {} 信息 {} 成功 建仓 并录入到 {} 数量 {} 当前值 {}".format(direction, orderInfo, "{}_real_short_qty".format(token), orderInfo["origQty"], [float(item) for item in redisClient.lrangeKey("{}_real_short_qty".format(token), 0, -1)]))
                        redisClient.delKey(keyName)
                    # 判断是否为卖多
                    elif orderInfo["side"] == "SELL" and direction == "LONG" and direction == orderInfo["positionSide"]:
                        if int(redisClient.llenKey("{}_real_long_qty".format(token))) == 0:
                            continue
                        _check_number = checkListDetermine([float(item) for item in redisClient.lrangeKey("{}_real_long_qty".format(token), 0, -1)], orderInfo["origQty"])
                        if _check_number[0]:
                            for index, item in enumerate(_check_number[1]):
                                redisClient.delKey(keyName)
                                redisClient.lremKey("{}_real_long_qty".format(token), item, _check_number[2][index])
                                logger.info("订单方向 {} 信息 {} 成功 减仓 并录入到 {} 数量 {} 当前值 {}".format(direction, orderInfo, "{}_real_long_qty".format(token), orderInfo["origQty"], [float(item) for item in redisClient.lrangeKey("{}_real_long_qty".format(token), 0, -1)]))
                        else:
                            logger.error("订单方向 {} 信息 {} 失败 减仓 Key 值 {} 数量 {} 检测结果 {} 现有订单池 {}".format(direction, orderInfo, "{}_real_long_qty".format(token), orderInfo["origQty"], _check_number, [float(item) for item in redisClient.lrangeKey("{}_real_long_qty".format(token), 0, -1)]))
                    # 判断是否为卖空
                    elif orderInfo["side"] == "BUY" and direction == "SHORT" and direction == orderInfo["positionSide"]:
                        if int(redisClient.llenKey("{}_real_short_qty".format(token))) == 0:
                            continue
                        _check_number = checkListDetermine([float(item) for item in redisClient.lrangeKey("{}_real_short_qty".format(token), 0, -1)], orderInfo["origQty"])
                        if _check_number[0]:
                            for index, item in enumerate(_check_number[1]):
                                redisClient.delKey(keyName)
                                redisClient.lremKey("{}_real_short_qty".format(token), item, _check_number[2][index])
                                logger.info("订单方向 {} 信息 {} 成功 减仓 并录入到 {} 数量 {} 当前值 {}".format(direction, orderInfo, "{}_real_short_qty".format(token), orderInfo["origQty"], [float(item) for item in redisClient.lrangeKey("{}_real_short_qty".format(token), 0, -1)]))
                        else:
                            logger.error("订单方向 {} 信息 {} 失败 减仓 Key 值 {} 数量 {} 检测结果 {} 现有订单池 {}".format(direction, orderInfo, "{}_real_short_qty".format(token), orderInfo["origQty"], _check_number, [float(item) for item in redisClient.lrangeKey("{}_real_long_qty".format(token), 0, -1)]))
                # 判断如果是失效订单，直接移除
                elif orderInfo["status"] == "EXPIRED" or orderInfo["status"] == "CANCELED":
                    # 判断是否为买多
                    if orderInfo["side"] == "BUY" and direction == "LONG" and direction == orderInfo["positionSide"]:
                        if int(redisClient.llenKey("{}_long_qty".format(token))) == 0:
                            continue
                        _check_number = checkListDetermine([float(item) for item in redisClient.lrangeKey("{}_long_qty".format(token), 0, -1)], orderInfo["origQty"])
                        if _check_number[0]:
                            for index, item in enumerate(_check_number[1]):
                                redisClient.delKey(keyName)
                                redisClient.lremKey("{}_long_qty".format(token), item, _check_number[2][index])
                                logger.info("订单超时方向 {} 信息 {} 从 {} 中摘除数量 {}".format(direction, orderInfo, "{}_long_qty".format(token), orderInfo["origQty"]))
                    # 判断是否为买空
                    elif orderInfo["side"] == "SELL" and direction == "SHORT" and direction == orderInfo["positionSide"]:
                        if int(redisClient.llenKey("{}_short_qty".format(token))) == 0:
                            continue
                        _check_number = checkListDetermine([float(item) for item in redisClient.lrangeKey("{}_short_qty".format(token), 0, -1)], orderInfo["origQty"])
                        if _check_number[0]:
                            for index, item in enumerate(_check_number[1]):
                                redisClient.delKey(keyName)
                                redisClient.lremKey("{}_short_qty".format(token), item, _check_number[2][index])
                                logger.info("订单超时方向 {} 信息 {} 从 {} 中摘除数量 {}".format(direction, orderInfo, "{}_short_qty".format(token), orderInfo["origQty"]))
                    # 判断是否为卖多
                    elif orderInfo["side"] == "SELL" and direction == "LONG" and direction == orderInfo["positionSide"]:
                        redisClient.delKey(keyName)
                        redisClient.lpushKey("{}_long_qty".format(token), orderInfo["origQty"])
                        logger.info("订单超时方向 {} 信息 {} 从 {} 中增加数量 {}".format(direction, orderInfo, "{}_long_qty".format(token), orderInfo["origQty"]))
                        
                    # 判断是否为卖空
                    elif orderInfo["side"] == "BUY" and direction == "SHORT" and direction == orderInfo["positionSide"]:
                        redisClient.delKey(keyName)
                        redisClient.lpushKey("{}_short_qty".format(token), orderInfo["origQty"])
                        logger.info("订单超时方向 {} 信息 {} 从 {} 中增加数量 {}".format(direction, orderInfo, "{}_short_qty".format(token), orderInfo["origQty"]))
                        
        except Exception as err:
            logger.error("订单操作异常 {}".format(err))
