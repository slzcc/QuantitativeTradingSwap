# 简介

初学阶段 [摘抄](https://github.com/pynewstar/binance-modest-trader) 项目源码进行练习测试。

## 配置

配置文件 `conf/swapSymbol.json` 中，主要定义开单时对应币种初始数据:
```
	"ETHUSDT空": {
		"price_precision": 2,
		"qty_precision": 3,
		"min_qty": 0.1,       # 最小开仓购买币的数量
		"max_add_times": 8,   # 最大开单数量
		"profit": 0.4,        # 清仓波动zhi, 使用时单位会 * 100, 作为 % 使用
		"add_rate": 1.2,      # 加仓间隔, 使用时单位会 * 100, 作为 % 使用
		"position_times": 10, # 开仓倍数
		"T": 72,              # k 线获取时间(/h)
		"if_loss": 0,         # 亏损
		"use_time": 0.0
	},
```

配置文件 `conf/settings.py` 中, 主要定义使用的 API 类型以及一些全局配置信息等。

## 日志

日志都会记录在 `logs` 下, 日志类型目前分为两种:
	* 请求 API 日志
	* 运行日志

## 启动

如下命令会启动合约量化交易:

```
$ pip3 install -r package.pip
$ python3 main.py --symbol ETHUSDT多 --key xx --secret xx
```