#***********************************************
#
#      Filename: settings.py
#
#        Author: shilei@hotstone.com.cn
#   Description: 全局配置
#
#        Create: 2022-10-08 14:58:33
# Last Modified: 2022-10-08 14:58:33
#
#***********************************************

# API 类型
API_TYPE = "BinanceTestNet"

# 判定当前接口类型
if API_TYPE == "Binance":
    # 正式网络
    FUTURE_URL = "https://fapi.binance.com"
    SPOT_URL = "https://api.binance.com/api/v3"
elif API_TYPE == "BinanceTestNet":
    # 测试网络
    # View https://testnet.binancefuture.com/en/futures/BTCUSDT
    FUTURE_URL = "https://testnet.binancefuture.com"
    SPOT_URL = "https://testnet.binance.vision/api/v3"

# binance 当前发送请求的有效毫秒数
# https://binance-docs.github.io/apidocs/spot/en/#signed-trade-user_data-and-margin-endpoint-security
binance_recvWindow = 10000

# Request to Response Written to the log
ResponseLog = False

# 告警提示
MSG_TYPE = ""
if MSG_TYPE == "DingDing":
    token = ""
else:
    token = ""

# Requests Proxy
# 全局 HTTP 代理配置
PROXIES_DEFAULT_DATA = {}