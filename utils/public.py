#***********************************************
#
#      Filename: public.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 公共方法使用库
#
#        Create: 2022-10-10 16:53:32
# Last Modified: 2022-10-10 16:53:32
#
#***********************************************

from conf.settings import *
from utils.method import requestMethod as PublicRequestsMethod
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

import logging
import time
import re
import types

# 创建日志器对象
######################################## Logging __name__ #######################################
logger = logging.getLogger(__name__)

# 设置logger可输出日志级别范围
logger.setLevel(logging.DEBUG)

# 添加控制台handler，用于输出日志到控制台
console_handler = logging.StreamHandler()
# 日志输出到系统
# console_handler = logging.StreamHandler(stream=None）
# 添加日志文件handler，用于输出日志到文件中
#file_handler = logging.FileHandler(filename='logs/Events.log', encoding='UTF-8', when='H', interval=1, backupCount=12)
file_handler = TimedRotatingFileHandler(filename='logs/Events.log', encoding='UTF-8', when='H', interval=1, backupCount=12)

# 将handler添加到日志器中
#logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 设置格式并赋予handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# request 异常方法处理, 解决 requests 异常错误直接退出的问题
def PublicRequests(request={"url": "", "params": {}, "header": {}, "model": "GET", "timeout": 3, "verify": True, "proxies": {}}, recursive_abnormal={"recursive": 3, "count": 0, "alert_count": 3}):
    """
    :recursive_abnormal 异常递归 recursive 可重复次数 count 计数当前重复次数 alert_count 告警次数
    :example
    """
    if request["model"] == "GET":
        if recursive_abnormal["recursive"] == 0:
            return PublicRequestsMethod._Get(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"], "count": recursive_abnormal["count"], "alert_count": recursive_abnormal["alert_count"]})
        else:
            return PublicRequestsMethod._Get(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"] - 1, "count": recursive_abnormal["count"] + 1, "alert_count": recursive_abnormal["alert_count"]})
    elif request["model"] == "POST":
        if recursive_abnormal["recursive"] == 0:
            return PublicRequestsMethod._Post(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"], "count": recursive_abnormal["count"], "alert_count": recursive_abnormal["alert_count"]})
        else:
            return PublicRequestsMethod._Post(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"] - 1, "count": recursive_abnormal["count"] + 1, "alert_count": recursive_abnormal["alert_count"]})
    elif request["model"] == "DELETE":
        if recursive_abnormal["recursive"] == 0:
            return PublicRequestsMethod._Delete(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"], "count": recursive_abnormal["count"], "alert_count": recursive_abnormal["alert_count"]})
        else:
            return PublicRequestsMethod._Delete(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"] - 1, "count": recursive_abnormal["count"] + 1, "alert_count": recursive_abnormal["alert_count"]})

# 时间格式化
def changeTime(sec):
    """
    时间格式化
    :sec time.time()
    :return ep: 2022-10-10 17:16:40
    """
    base_time = datetime.strptime('1970-01-01 00:00:00.0', '%Y-%m-%d %H:%M:%S.%f')
    return str(base_time + timedelta(seconds=8 * 3600 + int(sec)))

def getClassENV(cls):
    """
    获取 Class 静态环境变量
    """
    _strTmp = ""
    for index, item in enumerate(dir(cls)):
        if not re.search('__', item):
            _cls = getattr(cls, item)
            if not isinstance(_cls, types.MethodType):
                if (index + 1) == len(dir(cls)):
                    _strTmp += "{}: {}".format(item, _cls)
                else:
                    _strTmp += "{}: {}, ".format(item, _cls)
    return _strTmp
