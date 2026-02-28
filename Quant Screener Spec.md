

# Quant Screener Spec
面向：Codex 实现一个可跑的 Python Demo（非自动下单），用于 A 股“类量化”筛选与执行辅助  

时区：Asia/Shanghai

数据源默认：AkShare（免费）。要求抽象 DataSource，便于未来换 Tushare。  

---

## 0. 目标与范围

### 0.1 目标
实现一个命令行可运行的 Demo：
1) **ETF 轮动（每周）**：计算 ETF 池的近 20 日涨幅 + 是否站上 20 日均线，输出排名与“本周建议持仓”。  
2) **趋势突破（每日）**：筛选 A 股候选（60日新高 + 放量 ≥ 1.5倍均量），输出候选清单。  
3) **风控与仓位建议（必做）**：对趋势突破候选，按“单笔风险 2%”计算建议股数/金额（A股100股一手取整）+ 默认止损（-8%）。  
4) **绩效统计（必做）**：从交易记录 trades.xlsx 读取已平仓交易，统计胜率/盈亏比/期望/连亏次数，并触发“连亏暂停交易”。  
5) **权益曲线（必做）**：基于交易记录生成 equity_curve.csv + equity_curve.png，并计算最大回撤。  
6) 输出到 Excel/CSV/PNG，便于人工照表执行交易。

### 0.2 非目标
- 不做券商实盘下单接口
- 不做分钟级/高频
- 不做复杂多因子/ML（demo 以规则为主）
- 不做完整历史回测（可选扩展）

---

## 1. 技术栈与依赖

- Python >= 3.10
- 依赖：
  - akshare
  - pandas
  - numpy
  - openpyxl（写 Excel）
  - matplotlib（画权益曲线）

安装：

```bash
pip install akshare pandas numpy openpyxl matplotlib
```

------

## **2. 项目结构（建议）**

```
quant_screener_demo/
  README.md
  requirements.txt (或 pyproject.toml)
  src/
    main.py
    config.py
    data_source/
      base.py
      akshare_impl.py
    logic/
      etf_rotation.py
      trend_breakout.py
      risk.py
      performance.py
      equity_curve.py
      filters.py
    output/
      writer.py
      logger.py
  outputs/
    (运行生成文件)
```



------

## **3. 配置（config.py 或 config.yaml）**

### **3.1 基础配置项（必须支持覆盖）**

```
RUN_DATE: 默认今天
OUTPUT_DIR: ./outputs

# ETF轮动
ETF_POOL:
  - {name: "沪深300", code: "510300"}
  - {name: "创业板", code: "159915"}
  - {name: "科创50", code: "588000"}
  - {name: "券商",   code: "512000"}
  - {name: "半导体", code: "512760"}
  - {name: "军工",   code: "512660"}
ETF_RET_WINDOW: 20
ETF_MA_WINDOW: 20
ETF_HISTORY_MIN_DAYS: 120

# 趋势突破（日线）
LOOKBACK_HIGH: 60
VOL_AVG_WINDOW: 20
VOL_MULTIPLIER: 1.5
MIN_HISTORY_DAYS: 200
EXCLUDE_ST: true

# 市值过滤（默认关闭，避免数据单位差异）
MKT_CAP_FILTER_ENABLED: false
MKT_CAP_MIN: 100e8
MKT_CAP_MAX: 800e8

# 扫描性能（demo 默认只扫部分）
SCAN_LIMIT: 500
SLEEP_SECONDS: 0.15

# 风控与仓位
ACCOUNT_CAPITAL: 20000
RISK_PER_TRADE_PCT: 0.02
DEFAULT_STOP_LOSS_PCT: 0.08
ROUND_LOT: 100

# 连亏暂停
MAX_CONSECUTIVE_LOSSES: 3
PAUSE_DAYS_AFTER_MAX_LOSS: 5
```

------

## **4. 数据源抽象（DataSource）**

### **4.1 接口定义（src/data_source/base.py）**

定义抽象类 DataSource，必须提供：

- get_a_spot() -> pd.DataFrame
  - 返回列：code(str), name(str), mktcap(float, optional)
- get_stock_daily(code: str) -> pd.DataFrame
  - 返回列：date(datetime/str), close(float), volume(float)
  - 必须按 date 升序
- get_etf_daily(code: str) -> pd.DataFrame
  - 返回列：date, close, volume(optional)

### **4.2 AkShare 实现（src/data_source/akshare_impl.py）**

要求：

- 适配 AkShare 返回中文列，统一 rename 为英文标准列：
  - 日期 -> date
  - 收盘 -> close
  - 成交量 -> volume
  - 代码 -> code
  - 名称 -> name
  - 总市值 -> mktcap（如存在）
- 字段缺失时：抛出带提示的异常（提示“接口字段可能变动，需更新映射”）
- 数据条数校验：
  - ETF：必须 >= ETF_HISTORY_MIN_DAYS，否则标记为不可用
  - 股票：必须 >= MIN_HISTORY_DAYS，否则跳过
- 降级策略（必须）：
  - 某只标的拉取失败：记录 warning，跳过，不影响整体运行

------

## **5. ETF 轮动策略（src/logic/etf_rotation.py）**

### **5.1 输入**

- ETF_POOL（name, code）
- 参数：RET_WINDOW=20, MA_WINDOW=20

### **5.2 计算规则**

对每个 ETF：

1. 拉取日线 df，取最近至少 ETF_HISTORY_MIN_DAYS
2. 计算：
   - retN = close / close.shift(RET_WINDOW) - 1
   - maN = close.rolling(MA_WINDOW).mean()
   - above_ma = close > maN
3. 取最后一行作为当前值

### **5.3 排名与建议**

- 按 retN 从高到低排序
- 建议持仓规则：
  - 若排名第1的 above_ma = True => decision = "BUY:<name>(<code>)"
  - 否则 => decision = "CASH"（空仓/现金）

### **5.4 输出字段（DataFrame）**

必须包含：

- name, code, close, retN, retN_pct, maN, above_ma, rank

  以及：

- decision（仅写在单独 summary 或所有行同列亦可）

------

## **6. 趋势突破筛选（src/logic/trend_breakout.py）**

### **6.1 输入**

- 股票快照池（get_a_spot）
- 参数：LOOKBACK_HIGH=60, VOL_AVG_WINDOW=20, VOL_MULTIPLIER=1.5
- 过滤项：EXCLUDE_ST

### **6.2 股票池过滤（src/logic/filters.py）**

- 若 EXCLUDE_ST=true：排除 name 含 “ST” 的股票
- 市值过滤（可选）：当 MKT_CAP_FILTER_ENABLED=true 且 mktcap 字段存在时：
  - mktcap in [MKT_CAP_MIN, MKT_CAP_MAX]
- Demo 扫描数量限制：
  - 取过滤后前 SCAN_LIMIT 条（或可按成交额/市值排序取前 N）

### **6.3 单只股票信号判断**

对每只股票 code：

1. 拉取日线 df（至少 MIN_HISTORY_DAYS，date 升序）
2. 取最近 MIN_HISTORY_DAYS（或最近 200~300 条）
3. 定义：
   - today_close = df.close.iloc[-1]
   - prev_high = max(df.close.iloc[-LOOKBACK_HIGH-1:-1])（不含今日）
   - is_60d_high = today_close > prev_high
   - avg_vol = mean(df.volume.iloc[-VOL_AVG_WINDOW-1:-1])
   - vol_ratio = df.volume.iloc[-1] / avg_vol（avg_vol=0 则 NaN）
   - vol_ok = vol_ratio >= VOL_MULTIPLIER
4. 入选条件：
   - is_60d_high == True AND vol_ok == True

### **6.4 输出字段（候选表）**

对每个候选股输出：

- code, name
- close
- is_60d_high (bool)
- vol_ratio (float, 保留2位)
- entry_price（demo=close）
- stop_price（默认=entry_price*(1-DEFAULT_STOP_LOSS_PCT)）
- suggested_shares（由风控模块计算）
- suggested_position_value（由风控模块计算）
- note（若触发暂停交易则写“暂停交易”，否则空）

------

## **7. 风控与仓位建议（src/logic/risk.py）— 必做**

### **7.1 单笔风险预算**

- risk_budget = ACCOUNT_CAPITAL * RISK_PER_TRADE_PCT

### **7.2 每股风险**

- risk_per_share = entry_price - stop_price
- 若 risk_per_share <= 0：返回 suggested_shares=0，并 note 标注无效止损

### **7.3 建议股数（按 100 股一手取整）**

- raw_shares = floor(risk_budget / risk_per_share)
- suggested_shares = floor(raw_shares / ROUND_LOT) * ROUND_LOT
- suggested_position_value = suggested_shares * entry_price

### **7.4 输出**

返回结构：

- risk_budget
- risk_per_share
- suggested_shares
- suggested_position_value

------

## **8. 交易记录与绩效统计（src/logic/performance.py）— 必做**

### **8.1 交易记录文件**

- 文件：outputs/trades.xlsx（若不存在则创建空模板）

- Sheet：Trades

- 列（必须支持中英列名映射，但推荐统一英文）：

  

  - trade_id（可自动生成）
  - date_open（YYYY-MM-DD）
  - date_close（YYYY-MM-DD，可空）
  - symbol（code）
  - name
  - side（默认 LONG）
  - entry_price
  - exit_price（可空）
  - shares
  - fees（可选，默认0）

### **8.2 平仓判定**

- 仅统计已平仓：date_close 非空 AND exit_price 非空

### **8.3 计算字段（对每笔已平仓）**

- pnl_amount = (exit_price - entry_price) * shares - fees
- pnl_pct = (exit_price - entry_price) / entry_price
- is_win = pnl_amount > 0

### **8.4 统计指标（report 必须包含）**

- total_trades
- win_rate = wins / total_trades
- avg_win（仅 wins 的平均 pnl_amount）
- avg_loss（仅 losses 的平均 pnl_amount，负数）
- profit_factor = sum(pnl_amount>0) / abs(sum(pnl_amount<0))（若无亏损则给一个大值或 None）
- expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
- max_consecutive_losses（历史最大连亏）
- current_consecutive_losses（最近连续亏损）

### **8.5 连亏暂停规则（必做）**

- 若 current_consecutive_losses >= MAX_CONSECUTIVE_LOSSES：
  - TRADE_PAUSED = True
  - pause_until_date = RUN_DATE + PAUSE_DAYS_AFTER_MAX_LOSS（自然日即可）
  - 在趋势突破候选输出中 note 写 “暂停交易”
  - 在 report 中明确提示暂停状态

------

## **9. 权益曲线与最大回撤（src/logic/equity_curve.py）— 必做**

### **9.1 输入**

- 初始资金 ACCOUNT_CAPITAL
- 已平仓交易列表（按 date_close 升序）

### **9.2 计算**

- equity_0 = ACCOUNT_CAPITAL
- 对每个平仓日期 t：
  - equity_t = equity_{t-1} + pnl_amount_t（同一天多笔则合并）
- 计算峰值与回撤：
  - peak_t = max(peak_{t-1}, equity_t)
  - drawdown_t = (equity_t - peak_t) / peak_t
- max_drawdown = min(drawdown_t)

### **9.3 输出文件（必做）**

- outputs/equity_curve.csv：date, equity, drawdown
- outputs/equity_curve.png：一张图（date vs equity），用 matplotlib 画，默认样式即可
- max_drawdown 写入 report

------

## **10. 输出（src/output/writer.py）— 必做**

### **10.1 输出目录**

- 若 OUTPUT_DIR 不存在则创建

### **10.2 生成文件清单（每次运行尽量覆盖写入）**

- etf_rotation_rank.xlsx（含排名与 decision）
- etf_rotation_rank.csv
- trend_breakout_candidates.xlsx（含风控列）
- trend_breakout_candidates.csv
- trades.xlsx（若不存在则生成模板；若存在则不覆盖用户数据，只读取）
- report.xlsx（统计汇总 + 暂停信号 + max_drawdown）
- report.json（同上，便于程序读取）
- equity_curve.csv
- equity_curve.png

### **10.3 Excel 表结构建议**

- etf_rotation_rank.xlsx：Sheet Rank
- trend_breakout_candidates.xlsx：Sheet Candidates
- report.xlsx：Sheet Summary + Stats + Notes（可简化为一个）

------

## **11. CLI（src/main.py）— 必做**

### **11.1 命令**

- python -m src.main etf
- python -m src.main breakout
- python -m src.main all

### **11.2 参数**

- --output-dir
- --scan-limit
- --risk-per-trade（覆盖配置 RISK_PER_TRADE_PCT）
- --sleep（覆盖 SLEEP_SECONDS）

### **11.3 返回码**

- 成功：0
- 关键失败（例如依赖缺失、输出目录不可写）：非0

------

## **12. 日志与错误处理（src/output/logger.py）— 必做**

- 使用 Python logging

- 日志级别：

  

  - INFO：开始/结束、总数、输出文件路径
  - WARNING：单只标的拉取失败、字段缺失跳过
  - ERROR：关键模块失败（例如 DataSource 初始化失败）

  

- 失败策略：

  

  - 单只标的失败不影响整体
  - 任何一个模块失败应给出清晰错误信息

------

## **13. Demo 运行流程（all）**

python -m src.main all 需按顺序执行：

1. load config
2. init DataSource(AkShare)
3. run ETF rotation -> write outputs
4. run breakout candidates -> apply risk sizing -> write outputs
5. ensure trades.xlsx exists (create template if missing)
6. read trades.xlsx -> performance stats + pause logic -> write report
7. build equity curve + drawdown -> write csv/png + write report fields
8. 若 pause 触发：在 candidates 输出中写 note=暂停交易（覆盖写入 candidates 文件）

------

## **14. 验收标准（Acceptance Criteria）**

1. etf 命令能生成 ETF 排名表（xlsx+csv）并给出 decision

2. breakout 命令能生成候选清单（xlsx+csv），包含：

   

   - is_60d_high=true
   - vol_ratio>=1.5
   - stop_price=entry*(1-0.08)
   - suggested_shares 按 2% 风险计算并按 100 取整

   

3. all 命令能额外生成：

   

   - trades.xlsx（若不存在）
   - report.xlsx + report.json（含胜率、盈亏比、期望、连亏、暂停信号、最大回撤）
   - equity_curve.csv + equity_curve.png

   

4. 当 trades.xlsx 中存在连续亏损 >= 3 笔时：

   

   - report 标记暂停
   - candidates 的 note 标记暂停交易

   

------

## **15. 可选增强（非必须，写 TODO）**

- 多线程/异步拉取日线提升速度
- 限定股票池为沪深300/中证500成分
- 加入指数过滤（如沪深300站上MA20才允许做突破）
- 加入交易费用模型（印花税/佣金/过户费）

------

## **16. 备注（重要）**

- 数据源 AkShare 可能存在字段调整/限流/偶发失败，因此必须实现列映射与降级策略。
- Demo 阶段 entry_price=close 是近似；未来可扩展为“次日开盘价”。



```
如果你想让 Codex 更顺滑地一次性跑通，我建议你再补一句“实现优先级”给它：  
**先把 `all` 跑通并产出所有 outputs，再做字段美化/性能优化。**
```