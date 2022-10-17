#***********************************************
#
#      Filename: requestMethod.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 不可被直接调用的 requests 方法，主要目的是为了方便重复异常错误
#
#        Create: 2022-10-17 16:55:52
# Last Modified: 2022-10-17 16:55:52
#
#***********************************************

import requests
import time
from utils import public as PublicModels
from conf.settings import *

# 子方法, 不能直接被调用
def _Get(request={"url": "", "header": {}, "timeout": 3, "verify": True, "proxies": {}}, recursive_abnormal={"recursive": 3, "count": 0, "alert_count": 3}):
    """
    GET Request
    """
    if not "header" in request.keys():
        request["header"] = {}
    try:
        res = requests.get(url=request["url"], headers=request["header"], timeout=request["timeout"], verify=request["verify"], proxies=request["proxies"])
        if ResponseLog:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "GET", "", request["header"], res.json()))
        else:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "GET", "", request["header"], "如需要查看修改 ResponseLog 值为 True"))
        return res
    except Exception as err:
        # 当前请求出现异常
        if ResponseLog:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "GET", "", request["header"], res.json()))
        else:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "GET", "", request["header"], "如需要查看修改 ResponseLog 值为 True"))
        if recursive_abnormal["count"] >= recursive_abnormal["alert_count"]:
            recursive_abnormal["alert_count"] = recursive_abnormal["alert_count"] + 1
            # 当出现错误时，并达到 alert_count 数量进行处理
            return {}
        else:
            time.sleep(5)
            PublicModels.logger.info("请求地址 {} 异常, 错误提示 {}, 正在准备第 {} 次尝试".format(request["url"], err, recursive_abnormal["count"] + 1))
            return _Get(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"] - 1, "count": recursive_abnormal["count"] + 1, "alert_count": recursive_abnormal["alert_count"]})

# 子方法, 不能直接被调用
def _Post(request={"url": "", "params": {}, "header": {}, "timeout": 3, "verify": True, "proxies": {}}, recursive_abnormal={"recursive": 3, "count": 0, "alert_count": 3}):
    """
    Post Request
    """
    if not "header" in request.keys():
        request["header"] = {}
    try:
        res = requests.post(url=request["url"], data=request["params"], headers=request["header"], timeout=request["timeout"], verify=request["verify"], proxies=request["proxies"])
        if ResponseLog:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], res.json()))
        else:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], "如需要查看修改 ResponseLog 值为 True"))
        return res
    except Exception as err:
        # 当前请求出现异常
        if ResponseLog:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], res.json()))
        else:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], "如需要查看修改 ResponseLog 值为 True"))
        if recursive_abnormal["count"] >= recursive_abnormal["alert_count"]:
            # 当出现错误时，并达到 alert_count 数量进行处理
            recursive_abnormal["alert_count"] = recursive_abnormal["alert_count"] + 1
            return {}
        else:
            time.sleep(5)
            PublicModels.logger.info("请求地址 {} 异常, 错误提示 {}, 正在准备第 {} 次尝试".format(request["url"], err, recursive_abnormal["count"] + 1))
            return _Post(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"] - 1, "count": recursive_abnormal["count"] + 1, "alert_count": recursive_abnormal["alert_count"]})

# 子方法, 不能直接被调用
def _Delete(request={"url": "", "params": {}, "header": {}, "timeout": 3, "verify": True, "proxies": {}}, recursive_abnormal={"recursive": 3, "count": 0, "alert_count": 3}):
    """
    Delete Request
    """
    if not "header" in request.keys():
        request["header"] = {}
    try:
        res = requests.delete(url=request["url"], data=request["params"], headers=request["header"], timeout=request["timeout"], verify=request["verify"], proxies=request["proxies"])
        if ResponseLog:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], res.json()))
        else:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], "如需要查看修改 ResponseLog 值为 True"))
        return res
    except Exception as err:
        # 当前请求出现异常
        if ResponseLog:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], res.json()))
        else:
            PublicModels.logger.info("Request Url: {}, Request Type: {}, Body: {}, Header: {}, Response: {}".format(request["url"], "POST", "", request["params"], request["header"], "如需要查看修改 ResponseLog 值为 True"))
        if recursive_abnormal["count"] >= recursive_abnormal["alert_count"]:
            # 当出现错误时，并达到 alert_count 数量进行处理
            recursive_abnormal["alert_count"] = recursive_abnormal["alert_count"] + 1
            return {}
        else:
            time.sleep(5)
            PublicModels.logger.info("请求地址 {} 异常, 错误提示 {}, 正在准备第 {} 次尝试".format(request["url"], err, recursive_abnormal["count"] + 1))
            return _Delete(request=request, recursive_abnormal={"recursive": recursive_abnormal["recursive"] - 1, "count": recursive_abnormal["count"] + 1, "alert_count": recursive_abnormal["alert_count"]})
