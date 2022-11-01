#***********************************************
#
#      Filename: tradeWS.py
#
#        Author: shilei@hotstone.com.cn
#   Description: Binance WebSocket 初始对象
#
#        Create: 2022-11-01 10:31:33
# Last Modified: 2022-11-01 10:31:33
#
#***********************************************

import json
import websocket

# 行情 ws
# Docs https://binance-docs.github.io/apidocs/spot/cn/#websocket
socket='wss://stream.binance.com:9443/ws'
#socket='wss://dstream.binance.com:9443/ws'

def on_open(self):
    # subscribe_message = {
    #     "method": "SUBSCRIBE",
    #     "params":
    #     [
    #      "btcusdt@depth@100ms"
    #      ],
    #     "id": 1
    #     }
    # subscribe_message = {
    #     "method": "SUBSCRIBE",
    #     "params":
    #     [
    #     "btcusdt@aggTrade",
    #     "btcusdt@depth"
    #     ],
    #     "id": 1
    #     }
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params":
        [
        "btcusdt@kline_1m",
        ],
        "id": 1
        }

    ws.send(json.dumps(subscribe_message))

def on_message(self, message):
    print("received a message", message)
def on_close(self):
    print("closed connection")

ws = websocket.WebSocketApp(socket,
                            on_open=on_open,
                            on_message=on_message,
                            on_close=on_close)

ws.run_forever()