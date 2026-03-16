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
import { fetchAnalysis, fetchAnalysisDates, fetchDates, fetchEtf, fetchEtfDates, fetchScreening } from "./api";
import type {
  AnalysisResponse,
  AnalysisStock,
  EtfPick,
  EtfResponse,
  PickedStock,
  ScreeningResponse,
  TrendPoint,
} from "./types";

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

function formatAxisDate(value: string) {
  if (!value || value.length < 10) return value;
  const month = String(Number(value.slice(5, 7)));
  const day = String(Number(value.slice(8, 10)));
  return `${month}.${day}`;
}

function getTonghuashunUrl(code: string) {
  return `https://stockpage.10jqka.com.cn/${code}/`;
}

function renderPrice(value?: number) {
  return typeof value === "number" ? value.toFixed(2) : "-";
}

function CandlestickChart({ points }: { points: TrendPoint[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const width = 560;
  const height = 220;
  const margin = { top: 12, right: 14, bottom: 30, left: 40 };

  if (points.length === 0) {
    return <div className="candle-empty">暂无走势数据</div>;
  }

  const highs = points.map((point) => point.high);
  const lows = points.map((point) => point.low);
  const rawMin = Math.min(...lows);
  const rawMax = Math.max(...highs);
  const priceSpan = Math.max(rawMax - rawMin, 0.5);
  const yMin = rawMin - priceSpan * 0.08;
  const yMax = rawMax + priceSpan * 0.08;
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const xStep = points.length > 1 ? plotWidth / (points.length - 1) : 0;
  const candleWidth = Math.max(6, Math.min(14, plotWidth / Math.max(points.length * 1.8, 1)));
  const gridValues = Array.from({ length: 4 }, (_, index) => yMin + ((yMax - yMin) / 3) * index).reverse();
  const tickIndexes =
    points.length <= 8
      ? points.map((_, index) => index)
      : Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])).filter(
          (index) => index >= 0
        );

  const getX = (index: number) => margin.left + (points.length === 1 ? plotWidth / 2 : index * xStep);
  const getY = (value: number) => margin.top + ((yMax - value) / (yMax - yMin)) * plotHeight;
  const hoveredPoint = hoveredIndex === null ? null : points[hoveredIndex];
  const closeLinePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${getX(index)} ${getY(point.close)}`)
    .join(" ");

  return (
    <div className="candle-chart" onMouseLeave={() => setHoveredIndex(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="股票蜡烛图走势">
        {gridValues.map((value) => {
          const y = getY(value);
          return (
            <g key={value}>
              <line x1={margin.left} x2={width - margin.right} y1={y} y2={y} stroke="#e7eef5" strokeDasharray="2 4" />
              <text x={margin.left - 8} y={y + 4} textAnchor="end" className="candle-axis-label">
                {value.toFixed(2)}
              </text>
            </g>
          );
        })}

        {points.map((point, index) => {
          const x = getX(index);
          const yHigh = getY(point.high);
          const yLow = getY(point.low);
          const yOpen = getY(point.open);
          const yClose = getY(point.close);
          const bodyTop = Math.min(yOpen, yClose);
          const bodyHeight = Math.max(Math.abs(yOpen - yClose), 2);
          const isUp = point.close >= point.open;
          const stroke = isUp ? "#cf1322" : "#08979c";
          const fill = isUp ? "#cf1322" : "#ffffff";
          return (
            <g key={`${point.date}-${index}`} onMouseEnter={() => setHoveredIndex(index)} className="candle-node">
              <line x1={x} x2={x} y1={yHigh} y2={yLow} stroke={stroke} strokeWidth={1.5} />
              <rect
                x={x - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                rx={2}
                fill={fill}
                stroke={stroke}
                strokeWidth={1.5}
              />
              <rect
                x={x - Math.max(candleWidth, 10)}
                y={margin.top}
                width={Math.max(candleWidth * 2, 20)}
                height={plotHeight}
                fill="transparent"
              />
            </g>
          );
        })}

        <path d={closeLinePath} className="close-line" />

        {points.map((point, index) => (
          <circle
            key={`close-point-${point.date}-${index}`}
            cx={getX(index)}
            cy={getY(point.close)}
            r={hoveredIndex === index ? 3.5 : 2.5}
            className="close-line-dot"
          />
        ))}

        {tickIndexes.map((index) => (
          <text
            key={`tick-${index}`}
            x={index === 0 ? margin.left : index === points.length - 1 ? width - margin.right : getX(index)}
            y={height - 8}
            textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}
            className="candle-axis-label"
          >
            {formatAxisDate(points[index].date)}
          </text>
        ))}
      </svg>

      {hoveredPoint ? (
        <div className="candle-tooltip">
          <strong>{hoveredPoint.date}</strong>
          <div>开盘 {renderPrice(hoveredPoint.open)}</div>
          <div>最高 {renderPrice(hoveredPoint.high)}</div>
          <div>最低 {renderPrice(hoveredPoint.low)}</div>
          <div>收盘 {renderPrice(hoveredPoint.close)}</div>
        </div>
      ) : null}
    </div>
  );
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
  const [view, setView] = useState<"stocks" | "analysis" | "etf">("stocks");
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [stockData, setStockData] = useState<ScreeningResponse | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisResponse | null>(null);
  const [etfData, setEtfData] = useState<EtfResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(STOCK_DEFAULT_PAGE_SIZE);

  const defaultPageSize = view === "etf" ? ETF_DEFAULT_PAGE_SIZE : STOCK_DEFAULT_PAGE_SIZE;

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    setSelectedDate("");
    setDates([]);
    setPage(1);
    setPageSize(defaultPageSize);

    const loader = view === "stocks" ? fetchDates : view === "analysis" ? fetchAnalysisDates : fetchEtfDates;
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

    const request =
      view === "stocks"
        ? fetchScreening(selectedDate)
        : view === "analysis"
          ? fetchAnalysis(selectedDate)
          : fetchEtf(selectedDate);
    request
      .then((res) => {
        if (!mounted) return;
        if (view === "stocks") {
          setStockData(res as ScreeningResponse);
        } else if (view === "analysis") {
          setAnalysisData(res as AnalysisResponse);
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
  const analysisStocks = analysisData?.stocks ?? [];
  const secondaryStocks =
    stockData?.secondary_stocks ?? stockData?.stocks?.filter((item) => item.is_secondary !== false) ?? [];
  const analysisUpCount = analysisStocks.filter((item) => item.return_pct > 0).length;
  const analysisDownCount = analysisStocks.filter((item) => item.return_pct < 0).length;
  const analysisFlatCount = analysisStocks.filter((item) => item.return_pct === 0).length;

  const trendMap = useMemo(() => {
    const map = new Map<string, ScreeningResponse["trends"][number]>();
    const trends = view === "analysis" ? analysisData?.trends ?? [] : stockData?.trends ?? [];
    for (const item of trends) {
      map.set(item.code, item);
    }
    return map;
  }, [analysisData, stockData, view]);

  const currentItems = view === "stocks" ? allStocks : view === "analysis" ? analysisStocks : (etfData?.etfs ?? []);
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
  const pagedAnalysisStocks = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return analysisStocks.slice(start, start + pageSize);
  }, [analysisStocks, currentPage, pageSize]);

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

  const analysisColumns = useMemo<ColumnsType<AnalysisStock>>(
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
        render: (_: string, record: AnalysisStock) => (
          <a href={getTonghuashunUrl(record.code)} target="_blank" rel="noreferrer">
            {record.name}
          </a>
        ),
      },
      { title: "加入价", dataIndex: "entry_price", key: "entry_price", width: 96, render: (value: number) => value.toFixed(2) },
      { title: "最新价", dataIndex: "latest_price", key: "latest_price", width: 96, render: (value: number) => value.toFixed(2) },
      { title: "区间收益", dataIndex: "return_pct", key: "return_pct", width: 108, render: renderPercent },
      { title: "加入时涨幅", dataIndex: "pct_chg", key: "pct_chg", width: 110, render: renderPercent },
      { title: "来源文件", dataIndex: "source_file", key: "source_file", width: 120 },
    ],
    []
  );

  const topTitle = view === "stocks" ? "A股日筛复盘面板" : view === "analysis" ? "股票观察池面板" : "ETF 周轮动决策面板";
  const topDesc =
    view === "stocks"
      ? "按筛选日期回看一筛全量名单，快速识别进入二筛的标的，并观察二筛股票后续价格走势。"
      : view === "analysis"
        ? "按加入日期查看盘中观察股票，并回看该股票自加入日至当前交易日的日线走势。"
      : "按周查看 ETF 强弱排序、均线站位和当周建议持仓，用于轮动决策复盘。";

  return (
    <div className="page">
      <Menu
        className="top-menu"
        mode="horizontal"
        selectedKeys={[view]}
        items={[
          { key: "stocks", label: "股票筛选" },
          { key: "analysis", label: "股票观察池" },
          { key: "etf", label: "ETF 周轮动" },
        ]}
        onClick={({ key }) => setView(key as "stocks" | "analysis" | "etf")}
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
                    const latestPoint = trend.points[trend.points.length - 1];
                    const dayHigh = latestPoint?.high ?? latestPoint?.open ?? latestPoint?.close;
                    const dayLow = latestPoint?.low ?? latestPoint?.open ?? latestPoint?.close;
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
                          <div>
                            <span>当日最高</span>
                            <strong>{renderPrice(dayHigh)}</strong>
                          </div>
                          <div>
                            <span>当日最低</span>
                            <strong>{renderPrice(dayLow)}</strong>
                          </div>
                        </div>

                        <CandlestickChart points={trend.points} />
                      </article>
                    );
                  })}
                </div>
              )}
            </Card>
          </Space>
        ) : view === "analysis" && analysisData ? (
          <Space direction="vertical" size={16} className="full-width">
            <Card bordered={false} className="overview-card">
              <div className="hero">
                <div className="hero-copy">
                  <Typography.Title level={2}>{topTitle}</Typography.Title>
                  <Typography.Paragraph>{topDesc}</Typography.Paragraph>
                </div>
                <div className="toolbar-card">
                  <Typography.Text type="secondary">加入日期</Typography.Text>
                  <Select
                    className="date-select compact"
                    value={selectedDate || undefined}
                    options={dates.map((date) => ({ label: date, value: date }))}
                    onChange={(value) => setSelectedDate(value)}
                    placeholder="选择加入日期"
                  />
                </div>
              </div>

              <div className="summary-strip analysis-summary-strip">
                <div className="summary-pill">
                  <span className="summary-title">加入日期</span>
                  <strong>{analysisData.date}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-title">最新交易日</span>
                  <strong>{analysisData.today}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-title">股票数量</span>
                  <strong>{analysisData.stocks.length}</strong>
                </div>
                <div className="summary-pill">
                  <span className="summary-title">区间收益涨跌比</span>
                  <strong className="summary-detail-text">
                    上涨 {analysisUpCount} / 下跌 {analysisDownCount} / 持平 {analysisFlatCount}
                  </strong>
                </div>
              </div>
            </Card>

            <Card bordered={false}>
              <div className="module-head">
                <div>
                  <Typography.Title level={5} className="module-title">
                    {analysisData.date} 分析股票列表
                  </Typography.Title>
                  <Typography.Text type="secondary">
                    表格和下方走势卡共用同一页股票，收益按加入时价格计算。
                  </Typography.Text>
                </div>
                <Pagination
                  current={currentPage}
                  pageSize={pageSize}
                  total={analysisStocks.length}
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

              <Table<AnalysisStock>
                rowKey="code"
                columns={analysisColumns}
                dataSource={pagedAnalysisStocks}
                pagination={false}
                scroll={{ x: 980 }}
                size="middle"
              />

              <div className="module-divider" />

              <div className="module-subhead">
                <Typography.Title level={5} className="module-title">
                  当页股票走势
                </Typography.Title>
                <Typography.Text type="secondary">
                  当前页 {pagedAnalysisStocks.length} 只股票，从 {analysisData.date} 到 {analysisData.today}
                </Typography.Text>
              </div>

              {pagedAnalysisStocks.length === 0 ? (
                <Empty description="当前页没有分析股票数据" />
              ) : (
                <div className="trend-grid">
                  {pagedAnalysisStocks.map((stock) => {
                    const trend = trendMap.get(stock.code);
                    if (!trend) return null;
                    const latestPoint = trend.points[trend.points.length - 1];
                    const dayHigh = latestPoint?.high ?? latestPoint?.open ?? latestPoint?.close;
                    const dayLow = latestPoint?.low ?? latestPoint?.open ?? latestPoint?.close;
                    return (
                      <article className="trend-card" key={stock.code}>
                        <div className="trend-head">
                          <div>
                            <strong>{stock.name}</strong>
                            <div className="trend-meta">
                              <span>{stock.code}</span>
                              <Tag color="gold">观察池</Tag>
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
                            <span>加入价</span>
                            <strong>{stock.entry_price.toFixed(2)}</strong>
                          </div>
                          <div>
                            <span>最新价</span>
                            <strong>{stock.latest_price.toFixed(2)}</strong>
                          </div>
                          <div>
                            <span>加入时涨幅</span>
                            <strong className={pctTone(stock.pct_chg)}>{stock.pct_chg.toFixed(2)}%</strong>
                          </div>
                          <div>
                            <span>当日最高</span>
                            <strong>{renderPrice(dayHigh)}</strong>
                          </div>
                          <div>
                            <span>当日最低</span>
                            <strong>{renderPrice(dayLow)}</strong>
                          </div>
                        </div>

                        <CandlestickChart points={trend.points} />
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
