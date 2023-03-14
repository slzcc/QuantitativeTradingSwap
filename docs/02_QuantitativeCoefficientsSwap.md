## 02_QuantitativeCoefficientsSwap

> 本机装备 redis 不能存在 auth, 当脚本启动时需要通过 127.0.0.1:6379 进行连接.

基于系数 `ETH/BTC` 币对进行交易, 当前脚本启动时, 基于合约下单 `ETH/USDT` 和 `BTC/USDT` 开多开空基于 `ETH/BTC` 的阀值。

启动命令:

```
$ python3 02_QuantitativeCoefficientsSwap.py --key xx --secret xx --token WtCAw1bLCV8
```

服务启动前需要配置 `conf/coefficientSymbol.json`

```
{
  "ETHBTC": {
    "price_precision": 1, # 无效数据
    "min_qty": 0.002,     # 最小下单 btc 数量
    "profit": 4,          # 利润值 %
    "min_profit": 0.02,   # 无效数据
    "ratio": 5            # 杠杆倍数
  }
}
```



### 暂停下单

当需要暂停后续下单需修改 redis 中的 `<token>_order_pause_coefficient` key 修改为 `true` 就会暂停后续下单。

> 暂停下单后不会影响当前的自动平仓.

### 强制平仓

当需要强制平仓可以修改 redis 中的 `<token>_forced_liquidation_coefficient` key 修改为 `true` 就会平仓。

> 平仓后会等待 5 秒继续下单, 如不在需要下单请于 `暂停下单` 同时启用.