# Quant Screener Spec

面向：本项目的策略规格定义  
时区：`Asia/Shanghai`  
定位：收盘后数据采集、规则筛选、结果记录与跟踪；不做自动下单

---

## 1. 范围

项目分成两条独立策略线：

1. A 股日筛
- 面向全市场 A 股
- 目标是找出当日满足“趋势突破 + 放量 + 风险收益结构”条件的候选股
- 结果写入 `screening_history`

2. ETF 周轮动
- 面向固定 ETF 池
- 目标是按近 20 日强弱做相对排序，并给出当周持仓建议
- 结果写入 `etf_history`

约束：

- `market_cache` 只存 A 股股票，不混入 ETF
- A 股筛选只读取本地数据库缓存，不在筛选阶段请求外部接口
- ETF 轮动只读取 `etf_cache`
- 两条策略线分别执行，不混跑

---

## 2. 数据口径

### 2.1 A 股日线字段

A 股筛选依赖以下字段：

- `code`
- `exchange`
- `name`
- `date`
- `close`
- `volume`
- `low`
- `pre_close`
- `open`
- `turnover`
- `mktcap`

说明：

- `market_cache.data` 只保留近 60 个交易日
- `mktcap` 存顶层，只保留最新值，不在每日 `data` 中重复存储

### 2.2 ETF 日线字段

ETF 轮动依赖以下字段：

- `code`
- `name`
- `date`
- `close`
- `volume`
- `low`

说明：

- `etf_cache.data` 至少需要覆盖 120 个交易日
- 当前保留上限可高于 120 日，以保证轮动计算稳定

---

## 3. 数据表规格

### 3.1 `market_cache`

用途：

- A 股近 60 交易日缓存

约束：

- `_id` 必须是 6 位股票代码
- 只允许股票文档，不允许快照、日志、元数据混入

结构：

```json
{
  "_id": "000001",
  "exchange": "SZ",
  "name": "平安银行",
  "mktcap": 209777975720.38,
  "updated_at": "datetime",
  "data": [
    {
      "date": "2026-03-06",
      "close": 10.81,
      "volume": 712641.18,
      "low": 10.70,
      "pre_close": 10.71,
      "open": 10.72,
      "turnover": 768553598.0
    }
  ]
}
```

### 3.2 `screening_history`

用途：

- 保存 A 股日筛结果

约束：

- `_id = [code].[run_date]`
- 同日同股票覆盖写入
- 保留历史日期记录，不删除历史

结构示例：

```json
{
  "_id": "000545.2026-03-06",
  "code": "000545",
  "run_date": "2026-03-06",
  "is_secondary": false
}
```

### 3.3 `etf_cache`

用途：

- 保存 ETF 历史日线

约束：

- `_id = ETF代码`

### 3.4 `etf_history`

用途：

- 保存 ETF 轮动排序结果

约束：

- `_id = [code].[run_date]`
- 同日同 ETF 覆盖写入

---

## 4. A 股日筛规格

### 4.1 股票池

来源：

- `market_cache`

前置规则：

- 默认排除 `ST`
- 历史数据不足 60 个交易日的不参与
- 若最新交易日不是目标交易日，不参与当次筛选

### 4.2 初筛规则

对每只股票，以最新交易日记为 `t`，计算：

1. 60 日新高
- `close_t > max(close_{t-60...t-1})`

2. 趋势过滤
- `close_t > MA20_t`
- `MA20_t = mean(close_{t-20...t-1})`

3. 可选加强项
- `MA5 > MA10 > MA20`
- 默认关闭

4. 放量
- `vol_ratio = volume_t / mean(volume_{t-20...t-1})`
- 默认要求：`vol_ratio >= 1.8`

5. 当日强度
- `pct_chg_t = close_t / close_{t-1} - 1`
- 默认要求：`pct_chg_t >= 0.04`

6. 结构止损
- `entry_price = close_t`
- `stop_price = min(low_t, MA10_t)`
- `risk_pct = (entry_price - stop_price) / entry_price`
- 若 `stop_price >= entry_price`，则剔除

初筛排序：

- `vol_score = abs(vol_ratio - 3.0)`
- 排序：`vol_score asc, code asc`

### 4.3 二次筛选规则

二筛恒定执行，不依赖初筛数量。

默认规则：

1. 量能过滤
- `2.0 <= vol_ratio <= 6.0`

2. 风险空间过滤
- `0.04 <= risk_pct <= 0.08`

3. 强度过滤
- 若存在 `pct_chg`，则要求 `pct_chg >= 0.04`

4. 价格过滤
- `close <= 60`

5. 均线乖离过滤
- `ma20_gap = (close - ma20_price) / ma20_price`
- 默认要求：`ma20_gap <= 0.10`

6. 市值过滤
- 默认区间：`100e8 <= mktcap <= 600e8`
- 默认缺失口径：`exclude`

二筛排序：

- `score = abs(vol_ratio - 3.0) * w1 + abs(risk_pct - 0.06) * w2 + ma20_gap * w3`
- 默认权重：
  - `w1 = 1.0`
  - `w2 = 20.0`
  - `w3 = 10.0`
- 排序：`score asc`

输出口径：

- 初筛命中股票全部写入 `screening_history`
- 二筛命中的股票在同一条记录上标记 `is_secondary = true`

---

## 5. ETF 周轮动规格

### 5.1 ETF 池

当前固定池：

- `510300` 沪深300
- `159915` 创业板
- `588000` 科创50
- `512000` 券商
- `512760` 半导体
- `512660` 军工

### 5.2 轮动指标

对每只 ETF，以最新交易日记为 `t`：

1. 近 20 日涨幅
- `ret20 = close_t / close_{t-20} - 1`

2. 20 日均线
- `ma20 = mean(close_{t-19...t})`

3. 是否站上 20 日均线
- `above_ma20 = close_t > ma20`

历史要求：

- 至少有 120 个交易日数据才参与排序

### 5.3 排序与决策

排序规则：

- 按 `ret20 desc`

决策规则：

- 取排序第 1 名
- 若该 ETF `above_ma20 = true`，则输出：
  - `BUY:<name>(<code>)`
- 否则输出：
  - `CASH`

输出口径：

- 当次 ETF 池全部排序结果写入 `etf_history`
- 每条记录保留：
  - `code`
  - `run_date`
  - `rank`
  - `ret20`
  - `above_ma20`
  - `decision`

---

## 6. 流程边界

### 6.1 A 股流程

日流程分成两个阶段：

1. 数据采集阶段
- 拉取当日全量股票日线
- 补充最新 `mktcap`
- 更新 `market_cache`

2. 筛选阶段
- 只读 `market_cache`
- 执行初筛与二筛
- 写入 `screening_history`

补充约束：

- 若当日快照不包含今日交易日数据，则不继续执行 `mktcap` 补充与筛选

### 6.2 ETF 流程

周流程分成两个阶段：

1. 数据采集阶段
- 拉取 ETF 历史日线
- 更新 `etf_cache`

2. 轮动阶段
- 只读 `etf_cache`
- 排序并生成当周建议
- 写入 `etf_history`

---

## 7. 非目标

当前不做：

- 自动下单
- 分钟级交易策略
- 多因子打分框架
- 回测系统
- 风控执行引擎
