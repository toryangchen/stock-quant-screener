import { useEffect, useMemo, useState } from "react";
import type { ColumnsType } from "antd/es/table";
import { QuestionCircleOutlined } from "@ant-design/icons";
import {
  Alert,
  Card,
  Empty,
  Menu,
  Pagination,
  Popover,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchDates, fetchEtf, fetchEtfDates, fetchScreening } from "./api";
import type { EtfPick, EtfResponse, PickedStock, ScreeningResponse } from "./types";

const STOCK_DEFAULT_PAGE_SIZE = 6;
const ETF_DEFAULT_PAGE_SIZE = 6;
const PRIMARY_RULES = [
  "近 60 日收盘突破前高",
  "收盘站上 MA20",
  "当日涨幅不低于 4%",
  "量比不低于 1.8",
];
const SECONDARY_RULES = [
  "量比控制在 2 到 6 倍",
  "止损风险控制在 4% 到 8%",
  "股价不高于 60 元",
  "距 MA20 不超过 10%，再按评分排序",
];

function pctTone(value: number) {
  return value >= 0 ? "up" : "down";
}

function renderPercent(value: number) {
  return <span className={pctTone(value)}>{value.toFixed(2)}%</span>;
}

function renderNumber(value: number, digits = 2) {
  return value ? value.toFixed(digits) : "-";
}

function formatShortDate(value: string) {
  if (!value || value.length < 10) return value;
  return value.slice(5);
}

function getTonghuashunUrl(code: string) {
  return `https://stockpage.10jqka.com.cn/${code}/`;
}

function RuleBubble({ title, items }: { title: string; items: string[] }) {
  return (
    <Popover
      trigger="hover"
      placement="bottomRight"
      overlayClassName="logic-popover"
      content={
        <div className="logic-bubble">
          <strong>{title}</strong>
          <ul>
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      }
    >
      <span className="logic-help" aria-label={`${title}说明`}>
        <QuestionCircleOutlined />
      </span>
    </Popover>
  );
}

export default function App() {
  const [view, setView] = useState<"stocks" | "etf">("stocks");
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [stockData, setStockData] = useState<ScreeningResponse | null>(null);
  const [etfData, setEtfData] = useState<EtfResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(STOCK_DEFAULT_PAGE_SIZE);

  const defaultPageSize = view === "stocks" ? STOCK_DEFAULT_PAGE_SIZE : ETF_DEFAULT_PAGE_SIZE;

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    setSelectedDate("");
    setDates([]);
    setPage(1);
    setPageSize(defaultPageSize);

    const loader = view === "stocks" ? fetchDates : fetchEtfDates;
    loader()
      .then((res) => {
        if (!mounted) return;
        setDates(res);
        setSelectedDate(res[res.length - 1] ?? "");
      })
      .catch((e: Error) => {
        if (!mounted) return;
        setError(e.message);
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [view, defaultPageSize]);

  useEffect(() => {
    if (!selectedDate) return;
    let mounted = true;
    setLoading(true);
    setError("");
    setPage(1);
    setPageSize(defaultPageSize);

    const request = view === "stocks" ? fetchScreening(selectedDate) : fetchEtf(selectedDate);
    request
      .then((res) => {
        if (!mounted) return;
        if (view === "stocks") {
          setStockData(res as ScreeningResponse);
        } else {
          setEtfData(res as EtfResponse);
        }
      })
      .catch((e: Error) => {
        if (!mounted) return;
        setError(e.message);
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [selectedDate, view, defaultPageSize]);

  const allStocks = stockData?.primary_stocks ?? stockData?.stocks ?? [];
  const secondaryStocks =
    stockData?.secondary_stocks ?? stockData?.stocks?.filter((item) => item.is_secondary !== false) ?? [];

  const trendMap = useMemo(() => {
    const map = new Map<string, ScreeningResponse["trends"][number]>();
    if (!stockData) return map;
    for (const item of stockData.trends) {
      map.set(item.code, item);
    }
    return map;
  }, [stockData]);

  const currentItems = view === "stocks" ? allStocks : (etfData?.etfs ?? []);
  const totalPages = Math.max(1, Math.ceil(currentItems.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedStocks = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return allStocks.slice(start, start + pageSize);
  }, [allStocks, currentPage, pageSize]);
  const pagedEtfs = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return (etfData?.etfs ?? []).slice(start, start + pageSize);
  }, [etfData, currentPage, pageSize]);

  const stockColumns = useMemo<ColumnsType<PickedStock>>(
    () => [
      {
        title: "代码",
        dataIndex: "code",
        key: "code",
        width: 108,
        fixed: "left",
        render: (value: string) => (
          <a href={getTonghuashunUrl(value)} target="_blank" rel="noreferrer">
            {value}
          </a>
        ),
      },
      {
        title: "名称",
        dataIndex: "name",
        key: "name",
        width: 120,
        fixed: "left",
        render: (_: string, record: PickedStock) => (
          <a href={getTonghuashunUrl(record.code)} target="_blank" rel="noreferrer">
            {record.name}
          </a>
        ),
      },
      {
        title: "状态",
        dataIndex: "is_secondary",
        key: "is_secondary",
        width: 88,
        render: (value: boolean) => (value ? <Tag color="magenta">二筛</Tag> : <Tag color="blue">一筛</Tag>),
      },
      { title: "入选价", dataIndex: "entry_price", key: "entry_price", width: 96, render: (value: number) => value.toFixed(2) },
      { title: "最新价", dataIndex: "latest_price", key: "latest_price", width: 96, render: (value: number) => value.toFixed(2) },
      { title: "区间收益", dataIndex: "return_pct", key: "return_pct", width: 102, render: renderPercent },
      { title: "当日涨幅", dataIndex: "pct_chg", key: "pct_chg", width: 102, render: renderPercent },
      { title: "20日涨幅", dataIndex: "ret_20_stock", key: "ret_20_stock", width: 108, render: renderPercent },
      { title: "量比", dataIndex: "vol_ratio", key: "vol_ratio", width: 84, render: (value: number) => value.toFixed(2) },
      { title: "量能分", dataIndex: "vol_score", key: "vol_score", width: 90, render: (value: number) => value.toFixed(4) },
      { title: "风险", dataIndex: "risk_pct", key: "risk_pct", width: 88, render: (value: number) => <span className="risk-text">{value.toFixed(2)}%</span> },
      { title: "止损价", dataIndex: "stop_price", key: "stop_price", width: 92, render: (value: number) => value.toFixed(2) },
      { title: "MA10", dataIndex: "ma10_price", key: "ma10_price", width: 90, render: (value: number) => renderNumber(value, 3) },
      { title: "MA20", dataIndex: "ma20_price", key: "ma20_price", width: 90, render: (value: number) => renderNumber(value, 3) },
      { title: "市值(亿)", dataIndex: "mkt_cap", key: "mkt_cap", width: 100, render: (value: number) => renderNumber(value, 2) },
      { title: "评分", dataIndex: "score", key: "score", width: 88, render: (value: number) => renderNumber(value, 4) },
    ],
    []
  );

  const etfColumns = useMemo<ColumnsType<EtfPick>>(
    () => [
      { title: "排名", dataIndex: "rank", key: "rank", width: 80 },
      { title: "代码", dataIndex: "code", key: "code", width: 110 },
      { title: "名称", dataIndex: "name", key: "name", width: 120 },
      { title: "20日涨幅", dataIndex: "ret_pct", key: "ret_pct", width: 110, render: renderPercent },
      { title: "收盘价", dataIndex: "close", key: "close", width: 96, render: (value: number) => value.toFixed(3) },
      { title: "均线价", dataIndex: "ma_price", key: "ma_price", width: 96, render: (value: number) => value.toFixed(3) },
      {
        title: "是否站上均线",
        dataIndex: "above_ma",
        key: "above_ma",
        width: 120,
        render: (value: boolean) => (value ? <Tag color="green">是</Tag> : <Tag>否</Tag>),
      },
      { title: "本周决策", dataIndex: "decision", key: "decision", width: 220 },
    ],
    []
  );

  const topTitle = view === "stocks" ? "A股日筛复盘面板" : "ETF 周轮动决策面板";
  const topDesc =
    view === "stocks"
      ? "按筛选日期回看一筛全量名单，快速识别进入二筛的标的，并观察二筛股票后续价格走势。"
      : "按周查看 ETF 强弱排序、均线站位和当周建议持仓，用于轮动决策复盘。";

  return (
    <div className="page">
      <Menu
        className="top-menu"
        mode="horizontal"
        selectedKeys={[view]}
        items={[
          { key: "stocks", label: "股票筛选" },
          { key: "etf", label: "ETF 周轮动" },
        ]}
        onClick={({ key }) => setView(key as "stocks" | "etf")}
      />

      {error && <Alert className="block-gap" type="error" message={error} showIcon />}

      <Spin spinning={loading}>
        {view === "stocks" && stockData ? (
          <Space direction="vertical" size={16} className="full-width">
            <Card bordered={false} className="overview-card">
              <div className="hero">
                <div className="hero-copy">
                  <Typography.Title level={2}>{topTitle}</Typography.Title>
                  <Typography.Paragraph>{topDesc}</Typography.Paragraph>
                </div>
                <div className="toolbar-card">
                  <Typography.Text type="secondary">筛选日期</Typography.Text>
                  <Select
                    className="date-select compact"
                    value={selectedDate || undefined}
                    options={dates.map((date) => ({ label: date, value: date }))}
                    onChange={(value) => setSelectedDate(value)}
                    placeholder="选择筛选日期"
                  />
                </div>
              </div>

              <div className="summary-strip">
                <div className="summary-pill">
                  <span className="summary-title">筛选日期</span>
                  <strong>{stockData.date}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-title">最新交易日</span>
                  <strong>{stockData.today}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-label-with-help">
                    <span className="logic-inline-item">
                      二筛
                      <RuleBubble title="二筛逻辑" items={SECONDARY_RULES} />
                    </span>
                    <span className="logic-slash">/</span>
                    <span className="logic-inline-item">
                      一筛
                      <RuleBubble title="一筛逻辑" items={PRIMARY_RULES} />
                    </span>
                  </span>
                  <strong>{secondaryStocks.length} / {allStocks.length}</strong>
                </div>
              </div>
            </Card>

            <Card bordered={false}>
              <div className="module-head">
                <div>
                  <Typography.Title level={5} className="module-title">
                    {stockData.date} 筛选股票列表
                  </Typography.Title>
                  <Typography.Text type="secondary">
                    当前页表格和下方走势卡共用同一组股票。
                  </Typography.Text>
                </div>
                <Pagination
                  current={currentPage}
                  pageSize={pageSize}
                  total={allStocks.length}
                  showSizeChanger
                  pageSizeOptions={[6, 12, 18, 24]}
                  showTotal={(total, range) => `${range[0]}-${range[1]} / ${total}`}
                  onChange={(nextPage, nextPageSize) => {
                    setPage(nextPage);
                    setPageSize(nextPageSize);
                  }}
                  onShowSizeChange={(_, size) => {
                    setPage(1);
                    setPageSize(size);
                  }}
                />
              </div>

              <Table<PickedStock>
                rowKey="code"
                columns={stockColumns}
                dataSource={pagedStocks}
                pagination={false}
                scroll={{ x: 1680 }}
                size="middle"
              />

              <div className="module-divider" />

              <div className="module-subhead">
                <Typography.Title level={5} className="module-title">
                  当页股票走势
                </Typography.Title>
                <Typography.Text type="secondary">
                  当前页 {pagedStocks.length} 只股票，从 {stockData.date} 到 {stockData.today}
                </Typography.Text>
              </div>

              {pagedStocks.length === 0 ? (
                <Empty description="当前页没有股票数据" />
              ) : (
                <div className="trend-grid">
                  {pagedStocks.map((stock, idx) => {
                    const trend = trendMap.get(stock.code);
                    if (!trend) return null;
                    const tone = `hsl(${(idx * 47) % 360}, 72%, 42%)`;
                    return (
                      <article className="trend-card" key={stock.code}>
                        <div className="trend-head">
                          <div>
                            <strong>{stock.name}</strong>
                            <div className="trend-meta">
                              <span>{stock.code}</span>
                              {stock.is_secondary ? <Tag color="magenta">二筛</Tag> : <Tag color="blue">一筛</Tag>}
                            </div>
                          </div>
                          <div className="trend-stats">
                            <span className={pctTone(stock.return_pct)}>
                              {stock.return_pct >= 0 ? "+" : ""}
                              {stock.return_pct.toFixed(2)}%
                            </span>
                            <small>区间收益</small>
                          </div>
                        </div>

                        <div className="trend-summary">
                          <div>
                            <span>入选价</span>
                            <strong>{stock.entry_price.toFixed(2)}</strong>
                          </div>
                          <div>
                            <span>最新价</span>
                            <strong>{stock.latest_price.toFixed(2)}</strong>
                          </div>
                          <div>
                            <span>20日涨幅</span>
                            <strong className={pctTone(stock.ret_20_stock)}>{stock.ret_20_stock.toFixed(2)}%</strong>
                          </div>
                        </div>

                        <ResponsiveContainer width="100%" height={220}>
                          <AreaChart data={trend.points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                            <defs>
                              <linearGradient id={`trend-fill-${stock.code}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor={tone} stopOpacity={0.22} />
                                <stop offset="100%" stopColor={tone} stopOpacity={0.02} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid stroke="#e7eef5" strokeDasharray="2 4" vertical={false} />
                            <XAxis
                              dataKey="date"
                              tickFormatter={formatShortDate}
                              tick={{ fontSize: 11, fill: "#64748b" }}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis
                              domain={["auto", "auto"]}
                              tick={{ fontSize: 11, fill: "#64748b" }}
                              axisLine={false}
                              tickLine={false}
                              width={42}
                            />
                            <Tooltip
                              formatter={(value: number) => [`${Number(value).toFixed(2)}`, "收盘价"]}
                              labelFormatter={(label) => `日期 ${label}`}
                              contentStyle={{
                                borderRadius: 12,
                                border: "1px solid #dbe4f0",
                                boxShadow: "0 10px 30px rgba(15,23,42,0.08)",
                              }}
                            />
                            <Area
                              type="monotone"
                              dataKey="close"
                              stroke="none"
                              fill={`url(#trend-fill-${stock.code})`}
                            />
                            <Line
                              type="monotone"
                              dataKey="close"
                              stroke={tone}
                              dot={false}
                              strokeWidth={2.5}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </article>
                    );
                  })}
                </div>
              )}
            </Card>
          </Space>
        ) : view === "etf" && etfData ? (
          <Space direction="vertical" size={16} className="full-width">
            <Card bordered={false} className="overview-card">
              <div className="hero">
                <div className="hero-copy">
                  <Typography.Title level={2}>{topTitle}</Typography.Title>
                  <Typography.Paragraph>{topDesc}</Typography.Paragraph>
                </div>
                <div className="toolbar-card">
                  <Typography.Text type="secondary">轮动日期</Typography.Text>
                  <Select
                    className="date-select compact"
                    value={selectedDate || undefined}
                    options={dates.map((date) => ({ label: date, value: date }))}
                    onChange={(value) => setSelectedDate(value)}
                    placeholder="选择轮动日期"
                  />
                </div>
              </div>

              <div className="summary-strip">
                <div className="summary-pill">
                  <span className="summary-title">轮动日期</span>
                  <strong>{etfData.date}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-title">ETF 数量</span>
                  <strong>{etfData.etfs.length}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-title">本周决策</span>
                  <strong>{etfData.decision || "-"}</strong>
                </div>
              </div>
            </Card>

            <Card
              bordered={false}
              title={`${etfData.date} ETF 轮动结果`}
              extra={
                <Pagination
                  current={currentPage}
                  pageSize={pageSize}
                  total={etfData.etfs.length}
                  showSizeChanger
                  pageSizeOptions={[6, 12, 18, 24]}
                  showTotal={(total, range) => `${range[0]}-${range[1]} / ${total}`}
                  onChange={(nextPage, nextPageSize) => {
                    setPage(nextPage);
                    setPageSize(nextPageSize);
                  }}
                  onShowSizeChange={(_, size) => {
                    setPage(1);
                    setPageSize(size);
                  }}
                />
              }
            >
              <Table<EtfPick>
                rowKey="code"
                columns={etfColumns}
                dataSource={pagedEtfs}
                pagination={false}
                scroll={{ x: 980 }}
                size="middle"
              />
            </Card>
          </Space>
        ) : !loading ? (
          <Card bordered={false}>
            <Empty description="暂无数据" />
          </Card>
        ) : null}
      </Spin>
    </div>
  );
}
