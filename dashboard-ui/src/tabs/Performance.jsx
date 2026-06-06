/**
 * Performance tab — cumulative P&L chart, daily/weekly/monthly tables,
 * per-pair bar chart, per-regime breakdown.
 *
 * Charts use a pure SVG sparkline approach (no external lib needed for these
 * small charts). The cumulative P&L line uses the same SVG technique scaled
 * up to a card-width chart.
 */
import { useMemo } from "react";

import Card from "../components/Card";
import Table from "../components/Table";
import Stat from "../components/Stat";
import { usePolling } from "../api/hooks";
import {
  getDailyPerformance,
  getWeeklyPerformance,
  getMonthlyPerformance,
  getPairPerformance,
  getProfitSummary,
} from "../api/client";
import { formatRelative, formatDateTime } from "../utils/format";

// ─── Tiny SVG chart helpers ──────────────────────────────────────────────────

function miniPath(values, w, h, color) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <polyline
      points={pts.join(" ")}
      fill="none"
      stroke={color}
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
  );
}

// ─── Cumulative P&L Line Chart ───────────────────────────────────────────────

// FreqTrade field-name helper — newer versions use abs_profit, older used profit_all_coin
function absProfit(d) {
  return d.abs_profit ?? d.profit_all_coin ?? d.profit_fiat ?? null;
}
function relProfit(d) {
  return d.rel_profit ?? d.profit_all_percent ?? d.profit_percent ?? null;
}

function CumulativePnlChart({ data }) {
  const days = useMemo(() => {
    if (!Array.isArray(data)) return [];
    return [...data]
      .sort((a, b) => new Date(a.date) - new Date(b.date))
      .filter((d) => absProfit(d) != null);
  }, [data]);

  const cumulative = useMemo(() => {
    let sum = 0;
    return days.map((d) => {
      sum += absProfit(d) ?? 0;
      return { date: d.date, value: sum };
    });
  }, [days]);

  if (cumulative.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-text-muted text-xs">
        No performance data yet
      </div>
    );
  }

  const values = cumulative.map((p) => p.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const range = max - min || 1;
  const W = 700;
  const H = 160;
  const PAD = { top: 12, right: 8, bottom: 24, left: 48 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  const xOf = (i) => PAD.left + (i / (values.length - 1)) * cw;
  const yOf = (v) => PAD.top + ch - ((v - min) / range) * ch;
  const y0 = yOf(0);

  const pts = values
    .map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`)
    .join(" ");

  // Area fill path
  const areaPath = [
    `M ${xOf(0).toFixed(1)},${y0.toFixed(1)}`,
    ...values.map((v, i) => `L ${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`),
    `L ${xOf(values.length - 1).toFixed(1)},${y0.toFixed(1)}`,
    "Z",
  ].join(" ");

  const lastVal = values[values.length - 1];
  const lineColor = lastVal >= 0 ? "#22c55e" : "#ef4444";
  const fillId = `pnl-fill-${lastVal >= 0 ? "pos" : "neg"}`;

  // Y-axis ticks (3 labels)
  const yTicks = [min, (min + max) / 2, max];

  // X-axis ticks (show first / middle / last date)
  const xDates = [
    cumulative[0]?.date,
    cumulative[Math.floor(cumulative.length / 2)]?.date,
    cumulative[cumulative.length - 1]?.date,
  ].filter(Boolean);

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", maxHeight: "180px" }}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Zero baseline */}
        <line
          x1={PAD.left}
          y1={y0}
          x2={W - PAD.right}
          y2={y0}
          stroke="#2b323b"
          strokeWidth="1"
          strokeDasharray="3,3"
        />

        {/* Y-axis ticks */}
        {yTicks.map((v, i) => (
          <g key={i}>
            <line
              x1={PAD.left - 4}
              y1={yOf(v)}
              x2={PAD.left}
              y2={yOf(v)}
              stroke="#2b323b"
              strokeWidth="1"
            />
            <text
              x={PAD.left - 6}
              y={yOf(v) + 4}
              textAnchor="end"
              fontSize="9"
              fill="#64748b"
              fontFamily="JetBrains Mono, monospace"
            >
              {v >= 0 ? "+" : ""}
              {v.toFixed(1)}
            </text>
          </g>
        ))}

        {/* X-axis date labels */}
        {xDates.map((date, i) => {
          const idx =
            i === 0
              ? 0
              : i === 1
              ? Math.floor(cumulative.length / 2)
              : cumulative.length - 1;
          const label = new Date(date).toLocaleDateString("en-GB", {
            month: "short",
            day: "numeric",
          });
          return (
            <text
              key={i}
              x={xOf(idx)}
              y={H - 4}
              textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
              fontSize="9"
              fill="#64748b"
              fontFamily="JetBrains Mono, monospace"
            >
              {label}
            </text>
          );
        })}

        {/* Area fill */}
        <path d={areaPath} fill={`url(#${fillId})`} />

        {/* Line */}
        <polyline
          points={pts}
          fill="none"
          stroke={lineColor}
          strokeWidth="1.5"
          strokeLinejoin="round"
        />

        {/* Last point dot */}
        <circle
          cx={xOf(values.length - 1)}
          cy={yOf(lastVal)}
          r="3"
          fill={lineColor}
        />
      </svg>
    </div>
  );
}

// ─── Daily / Weekly / Monthly tables ─────────────────────────────────────────

function periodColumns(labelKey, labelTitle) {
  return [
    { key: labelKey, label: labelTitle, mono: true },
    {
      key: "abs_profit",
      label: "P&L (USDT)",
      align: "right",
      render: (r) => {
        const v = absProfit(r);
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const cls = v >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={`font-mono ${cls}`}>
            {v >= 0 ? "+" : ""}
            {v.toFixed(2)}
          </span>
        );
      },
    },
    {
      key: "rel_profit",
      label: "P&L %",
      align: "right",
      render: (r) => {
        const v = relProfit(r);
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const cls = v >= 0 ? "text-profit" : "text-loss";
        // rel_profit is already a ratio (0.05 = 5%) in newer FreqTrade versions
        const pct = Math.abs(v) < 1 ? v * 100 : v;
        return (
          <span className={`font-mono ${cls}`}>
            {v >= 0 ? "+" : ""}
            {pct.toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: "trade_count",
      label: "Trades",
      align: "right",
      mono: true,
      render: (r) => r.trade_count ?? r.trades ?? "—",
    },
    {
      key: "winning_trades",
      label: "W/L",
      align: "right",
      mono: true,
      render: (r) =>
        r.winning_trades != null && r.losing_trades != null
          ? `${r.winning_trades}/${r.losing_trades}`
          : "—",
    },
  ];
}

function PeriodTable({ title, data, error, loading, lastUpdated, labelKey, labelTitle }) {
  // Sort newest-first regardless of API return order (FreqTrade returns desc but
  // we sort explicitly so the table is stable even if the API order ever changes).
  const rows = Array.isArray(data)
    ? [...data].sort((a, b) => new Date(b.date) - new Date(a.date))
    : [];
  const cols = periodColumns(labelKey, labelTitle);

  return (
    <Card title={title} subtitle={`${rows.length} periods`} lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
      ) : (
        <Table
          columns={cols}
          rows={rows}
          loading={loading && !data}
          emptyMessage={`No ${title.toLowerCase()} data`}
          maxHeight="320px"
        />
      )}
    </Card>
  );
}

// ─── Per-pair horizontal bar chart ───────────────────────────────────────────

function PairBarChart({ data }) {
  const pairs = useMemo(() => {
    if (!Array.isArray(data)) return [];
    return [...data]
      .sort((a, b) => (absProfit(b) ?? 0) - (absProfit(a) ?? 0))
      .slice(0, 20);
  }, [data]);

  if (pairs.length === 0) {
    return (
      <div className="text-xs text-text-muted italic p-4">No pair data</div>
    );
  }

  const absMax = Math.max(...pairs.map((p) => Math.abs(absProfit(p) ?? 0)), 0.01);

  return (
    <div className="space-y-1.5 py-1">
      {pairs.map((p) => {
        const v = absProfit(p) ?? 0;
        const pct = (Math.abs(v) / absMax) * 100;
        const isPos = v >= 0;
        return (
          <div key={p.key} className="flex items-center gap-2 min-h-[22px]">
            <div className="w-20 text-xxs font-mono text-text-secondary truncate shrink-0 text-right">
              {(p.key ?? "").replace("/USDT:USDT", "").replace("/USDT", "")}
            </div>
            <div className="flex-1 flex items-center gap-1.5">
              <div
                className="h-4 rounded-sm"
                style={{
                  width: `${pct}%`,
                  minWidth: 2,
                  background: isPos ? "#22c55e" : "#ef4444",
                  opacity: 0.85,
                }}
              />
              <span
                className={`text-xxs font-mono shrink-0 ${isPos ? "text-profit" : "text-loss"}`}
              >
                {isPos ? "+" : ""}
                {v.toFixed(2)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Summary stat strip ───────────────────────────────────────────────────────

function SummaryStrip({ data }) {
  if (!data) return null;

  const winPct =
    data.winning_trades != null && data.losing_trades != null
      ? (data.winning_trades / (data.winning_trades + data.losing_trades)) * 100
      : null;

  const avgDur = data.holding_avg ?? data.avg_duration_mins;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
      <Stat
        label="Total P&L"
        value={data.profit_closed_coin != null ? data.profit_closed_coin.toFixed(2) : "—"}
        unit={data.profit_closed_coin != null ? "USDT" : ""}
        tone={
          data.profit_closed_coin == null
            ? "default"
            : data.profit_closed_coin >= 0
            ? "profit"
            : "loss"
        }
      />
      <Stat
        label="Closed Trades"
        value={data.closed_trade_count ?? "—"}
      />
      <Stat
        label="Win Rate"
        value={winPct != null ? winPct.toFixed(1) : "—"}
        unit={winPct != null ? "%" : ""}
        tone={winPct == null ? "default" : winPct >= 50 ? "profit" : "loss"}
      />
      <Stat
        label="Avg Hold"
        value={avgDur != null ? (avgDur / 60).toFixed(1) : "—"}
        unit={avgDur != null ? "h" : ""}
      />
      <Stat
        label="Profit Factor"
        value={data.profit_factor != null ? data.profit_factor.toFixed(2) : "—"}
        tone={
          data.profit_factor == null
            ? "default"
            : data.profit_factor >= 1.2
            ? "profit"
            : data.profit_factor >= 1
            ? "warn"
            : "loss"
        }
      />
    </div>
  );
}

// ─── Tab root ────────────────────────────────────────────────────────────────

export default function Performance() {
  const daily = usePolling(getDailyPerformance, 120000);
  const weekly = usePolling(getWeeklyPerformance, 120000);
  const monthly = usePolling(getMonthlyPerformance, 120000);
  const pairPerf = usePolling(getPairPerformance, 60000);
  const summary = usePolling(getProfitSummary, 60000);

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <SummaryStrip data={summary.data} />

      {/* Cumulative P&L chart */}
      <Card
        title="Cumulative P&L"
        subtitle="All-time, daily resolution"
        lastUpdated={daily.lastUpdated}
      >
        {daily.error ? (
          <p className="text-xs text-text-muted italic">Error: {daily.error}</p>
        ) : (
          <CumulativePnlChart data={daily.data} />
        )}
      </Card>

      {/* Daily + Weekly tables side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PeriodTable
          title="Daily P&L"
          data={daily.data}
          error={daily.error}
          loading={daily.loading}
          lastUpdated={daily.lastUpdated}
          labelKey="date"
          labelTitle="Date"
        />
        <PeriodTable
          title="Weekly P&L"
          data={weekly.data}
          error={weekly.error}
          loading={weekly.loading}
          lastUpdated={weekly.lastUpdated}
          labelKey="date"
          labelTitle="Week of"
        />
      </div>

      {/* Monthly + Per-pair bars side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PeriodTable
          title="Monthly P&L"
          data={monthly.data}
          error={monthly.error}
          loading={monthly.loading}
          lastUpdated={monthly.lastUpdated}
          labelKey="date"
          labelTitle="Month"
        />
        <Card
          title="Per-Pair P&L"
          subtitle="Top 20 by total profit"
          lastUpdated={pairPerf.lastUpdated}
        >
          {pairPerf.error ? (
            <p className="text-xs text-text-muted italic">
              Error: {pairPerf.error}
            </p>
          ) : pairPerf.loading && !pairPerf.data ? (
            <div className="p-6 text-center text-text-tertiary text-xs">
              Loading…
            </div>
          ) : (
            <PairBarChart data={pairPerf.data} />
          )}
        </Card>
      </div>
    </div>
  );
}
