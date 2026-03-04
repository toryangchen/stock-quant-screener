import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchDates, fetchScreening } from "./api";
import type { ScreeningResponse } from "./types";

export default function App() {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [data, setData] = useState<ScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    fetchDates()
      .then((res) => {
        if (!mounted) return;
        setDates(res);
        const def = res[res.length - 1] ?? "";
        setSelectedDate(def);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedDate) return;
    let mounted = true;
    setLoading(true);
    setError("");
    fetchScreening(selectedDate)
      .then((res) => {
        if (!mounted) return;
        setData(res);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
    return () => {
      mounted = false;
    };
  }, [selectedDate]);

  const trendMap = useMemo(() => {
    const m = new Map<string, ScreeningResponse["trends"][number]>();
    if (!data) return m;
    for (const t of data.trends) {
      m.set(t.code, t);
    }
    return m;
  }, [data]);

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>筛选后续跟踪面板</h1>
          <p>选择筛选日期，查看当日入选股票以及从该日到今天的走势。</p>
        </div>
        <div className="filter">
          <label htmlFor="date">筛选日期</label>
          <input
            id="date"
            type="date"
            value={selectedDate}
            min={dates[0]}
            max={dates[dates.length - 1]}
            onChange={(e) => setSelectedDate(e.target.value)}
          />
        </div>
      </header>

      {loading && <div className="panel">加载中...</div>}
      {error && <div className="panel error">{error}</div>}

      {!loading && data && (
        <>
          <section className="panel">
            <h2>{data.date} 入选股票 ({data.stocks.length})</h2>
            <table>
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>入选价</th>
                  <th>最新价</th>
                  <th>区间收益</th>
                </tr>
              </thead>
              <tbody>
                {data.stocks.map((s) => (
                  <tr key={s.code}>
                    <td>{s.code}</td>
                    <td>{s.name}</td>
                    <td>{s.entry_price.toFixed(2)}</td>
                    <td>{s.latest_price.toFixed(2)}</td>
                    <td className={s.return_pct >= 0 ? "up" : "down"}>{s.return_pct.toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>从 {data.date} 到 {data.today} 的个股趋势图</h2>
            <div className="trend-grid">
              {data.stocks.map((s, idx) => {
                const trend = trendMap.get(s.code);
                if (!trend) return null;
                return (
                  <article className="trend-card" key={s.code}>
                    <div className="trend-head">
                      <strong>{s.name}</strong>
                      <span>{s.code}</span>
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                      <LineChart data={trend.points}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis domain={["auto", "auto"]} />
                        <Tooltip />
                        <Line
                          type="monotone"
                          dataKey="close"
                          stroke={`hsl(${(idx * 47) % 360}, 72%, 42%)`}
                          dot={false}
                          strokeWidth={2}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
