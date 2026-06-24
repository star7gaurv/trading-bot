import { useMemo } from "react";

import Card from "../../../components/Card";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getSideSplit, getExitReasons, getOpenTrades } from "../../../api/client";

const EXIT_LABELS = {
  exit_signal: "Signal (model says close)",
  stop_loss: "Stop loss",
  trailing_stop_loss: "Trailing stop",
  time_limit_exit: "Time limit",
  roi: "ROI",
  liquidation: "Liquidation",
};

// ─── Tiny cumulative line ─────────────────────────────────────────────────────
function MiniEquity({ series, color }) {
  const values = (series || []).map((p) => p.value);
  if (values.length < 2) {
    return <div className="h-16 flex items-center justify-center text-xxs text-text-muted">not enough data</div>;
  }
  const W = 280, H = 64, PAD = 4;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const range = max - min || 1;
  const xOf = (i) => PAD + (i / (values.length - 1)) * (W - 2 * PAD);
  const yOf = (v) => PAD + (H - 2 * PAD) - ((v - min) / range) * (H - 2 * PAD);
  const y0 = yOf(0);
  const pts = values.map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 64 }} preserveAspectRatio="none">
      <line x1={PAD} y1={y0} x2={W - PAD} y2={y0} stroke="var(--color-border, #2b323b)" strokeWidth="1" strokeDasharray="3,3" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

// ─── Long vs Short ────────────────────────────────────────────────────────────
function SideColumn({ title, summary, series, color }) {
  const pnl = summary?.profit;
  const wr = summary?.wr;
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-semibold text-text-primary">{title}</span>
        <span className={`text-sm font-mono font-semibold ${pnl == null ? "text-text-muted" : pnl >= 0 ? "text-profit" : "text-loss"}`}>
          {pnl == null ? "—" : `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`}
          {pnl != null && <span className="text-xxs text-text-tertiary font-normal ml-1">USDT</span>}
        </span>
      </div>
      <MiniEquity series={series} color={color} />
      <div className="grid grid-cols-3 gap-1 mt-1.5 text-center">
        <div>
          <div className="text-xxs text-text-tertiary">Win rate</div>
          <div className={`text-xs font-mono ${wr == null ? "text-text-muted" : wr >= 0.5 ? "text-profit" : "text-loss"}`}>
            {wr == null ? "—" : `${(wr * 100).toFixed(0)}%`}
          </div>
        </div>
        <div>
          <div className="text-xxs text-text-tertiary">Trades</div>
          <div className="text-xs font-mono text-text-primary">{summary?.count ?? "—"}</div>
        </div>
        <div>
          <div className="text-xxs text-text-tertiary">Avg</div>
          <div className={`text-xs font-mono ${(summary?.avg_profit ?? 0) >= 0 ? "text-profit" : "text-loss"}`}>
            {summary?.avg_profit == null ? "—" : summary.avg_profit.toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Exit-reason waterfall ────────────────────────────────────────────────────
function ExitWaterfall({ items }) {
  const rows = useMemo(
    () => [...(items || [])].sort((a, b) => (b.profit ?? 0) - (a.profit ?? 0)),
    [items]
  );
  if (rows.length === 0) {
    return <p className="text-xs text-text-muted italic">No closed trades yet.</p>;
  }
  const absMax = Math.max(...rows.map((r) => Math.abs(r.profit ?? 0)), 0.01);
  const net = rows.reduce((a, r) => a + (r.profit ?? 0), 0);
  return (
    <div className="space-y-2">
      {rows.map((r) => {
        const v = r.profit ?? 0;
        const pct = (Math.abs(v) / absMax) * 100;
        const isPos = v >= 0;
        return (
          <div key={r.reason} className="flex items-center gap-2">
            <div className="w-40 text-xxs text-text-secondary truncate shrink-0">
              {EXIT_LABELS[r.reason] || r.reason.replace(/_/g, " ")}
            </div>
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-3.5 bg-elevated rounded-sm overflow-hidden flex">
                <div
                  className="h-full rounded-sm"
                  style={{ width: `${pct}%`, background: isPos ? "var(--color-profit, #22c55e)" : "var(--color-loss, #ef4444)", opacity: 0.85 }}
                />
              </div>
              <span className={`text-xxs font-mono shrink-0 w-24 text-right ${isPos ? "text-profit" : "text-loss"}`}>
                {isPos ? "+" : ""}{v.toFixed(2)} ({(r.wr * 100).toFixed(0)}% WR)
              </span>
            </div>
          </div>
        );
      })}
      <div className="border-t border-border pt-2 flex items-center justify-between text-xs">
        <span className="text-text-secondary font-medium">Net of all exits</span>
        <span className={`font-mono font-semibold ${net >= 0 ? "text-profit" : "text-loss"}`}>
          {net >= 0 ? "+" : ""}{net.toFixed(2)} USDT
        </span>
      </div>
    </div>
  );
}

// ─── Current exposure ─────────────────────────────────────────────────────────
function ExposureBars({ openTrades }) {
  const rows = useMemo(() => {
    const byPair = {};
    (Array.isArray(openTrades) ? openTrades : []).forEach((t) => {
      const p = (t.pair || "").replace("/USDT:USDT", "").replace("/USDT", "");
      byPair[p] = (byPair[p] || 0) + (t.stake_amount || 0);
    });
    return Object.entries(byPair)
      .map(([pair, stake]) => ({ pair, stake }))
      .sort((a, b) => b.stake - a.stake);
  }, [openTrades]);

  if (rows.length === 0) {
    return <p className="text-xs text-text-muted italic">No open positions right now.</p>;
  }
  const max = Math.max(...rows.map((r) => r.stake), 0.01);
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.pair} className="flex items-center gap-2">
          <div className="w-16 text-xxs font-mono text-text-secondary truncate shrink-0 text-right">{r.pair}</div>
          <div className="flex-1 flex items-center gap-2">
            <div className="h-4 rounded-sm bg-accent/70" style={{ width: `${(r.stake / max) * 100}%`, minWidth: 2 }} />
            <span className="text-xxs font-mono text-text-muted shrink-0">{r.stake.toFixed(0)} USDT</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Insights() {
  const split = usePolling(getSideSplit, 60000);
  const exits = usePolling(getExitReasons, 60000);
  const open = usePolling(getOpenTrades, 10000);

  return (
    <div className="space-y-3">
      <Card
        title="Long vs Short"
        subtitle="The two directions behave very differently — this splits them out"
        lastUpdated={split.lastUpdated}
      >
        {split.error ? (
          <p className="text-xs text-text-muted italic">Error: {split.error}</p>
        ) : (
          <div className="flex flex-col sm:flex-row gap-5">
            <SideColumn title="Long" summary={split.data?.long} series={split.data?.long_series} color="var(--color-profit, #22c55e)" />
            <div className="hidden sm:block w-px bg-border" />
            <SideColumn title="Short" summary={split.data?.short} series={split.data?.short_series} color="var(--color-loss, #ef4444)" />
          </div>
        )}
      </Card>

      <Card
        title={<span className="inline-flex items-center gap-1.5">Where the edge is<InfoTip text="Net profit grouped by why each trade closed. The model's exit signal is the real edge; stop-losses are where it bleeds." /></span>}
        subtitle="Net P&L by exit reason — signal exits earn, stop-losses bleed"
        lastUpdated={exits.lastUpdated}
      >
        <ExitWaterfall items={exits.data?.items} />
      </Card>

      <Card title="Current Exposure" subtitle="How much capital is in each pair right now" lastUpdated={open.lastUpdated}>
        <ExposureBars openTrades={open.data} />
      </Card>
    </div>
  );
}
