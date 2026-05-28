/**
 * Overview tab — at-a-glance dashboard.
 *
 * Rows:
 *   1. Stat strip (P&L today/7d/30d, WR, open positions, regime, F&G)
 *   2. Open positions mini-table + System health summary card
 *   3. Brain status + Walk-forward status
 */
import Card from "../components/Card";
import Stat from "../components/Stat";
import Table from "../components/Table";
import Badge from "../components/Badge";
import { usePolling } from "../api/hooks";
import {
  getProfitSummary,
  getOpenTrades,
  getRegimeCurrent,
  getCronStatus,
  getSystemHealth,
  getBrainQueue,
  getWfLatest,
  getBalance,
  getDailyPerformance,
} from "../api/client";
import {
  formatUsdt,
  formatNumber,
  formatPct,
  formatRelative,
  formatDuration,
} from "../utils/format";

// ─── Helpers ───
const REGIME_TONE = {
  BULL: "profit",
  EUPHORIA: "profit",
  NEUTRAL: "warn",
  BEAR: "loss",
  CRASH: "loss",
};

function safe(obj, key, fallback = null) {
  if (!obj || typeof obj !== "object") return fallback;
  const v = obj[key];
  return v == null ? fallback : v;
}

function trades7dPnl(profit) {
  // FT /profit endpoint exposes `profit_closed_coin` / `profit_all_coin` etc.
  // Best-effort: prefer absolute USDT field, fall back to nothing.
  return (
    safe(profit, "profit_closed_coin") ??
    safe(profit, "profit_all_coin") ??
    null
  );
}

// ─── Sub-panels ───
function StatStrip({ profit, openTrades, regime, dailyPerf, balance }) {
  const dailyArr = Array.isArray(dailyPerf) ? dailyPerf : (dailyPerf?.data || []);
  const todayEntry = dailyArr.length > 0 ? dailyArr[0] : null;
  const isActuallyToday = todayEntry && todayEntry.date === new Date().toISOString().split("T")[0];
  const today = isActuallyToday ? todayEntry.abs_profit : 0;
  const all = safe(profit, "profit_closed_coin");
  const winning = safe(profit, "winning_trades", 0) || 0;
  const losing = safe(profit, "losing_trades", 0) || 0;
  const total = winning + losing;
  const wr = total > 0 ? (winning / total) * 100 : null;

  const openCount = Array.isArray(openTrades) ? openTrades.length : 0;
  const totalOpenProfit = Array.isArray(openTrades) ? openTrades.reduce((acc, t) => acc + (t.profit_abs || 0), 0) : null;
  const balanceTotal = safe(balance, "total_bot") ?? safe(balance, "total");

  const regimeName = safe(regime, "regime", "—");
  const regimeTone = REGIME_TONE[regimeName] || "default";
  const regimeConf = safe(regime, "confidence");

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
      <Stat
        label="P&L Today"
        value={today != null ? today.toFixed(2) : "—"}
        unit={today != null ? "USDT" : ""}
        tone={today == null ? "default" : today >= 0 ? "profit" : "loss"}
      />
      <Stat
        label="P&L Closed"
        value={all != null ? all.toFixed(2) : "—"}
        unit={all != null ? "USDT" : ""}
        tone={all == null ? "default" : all >= 0 ? "profit" : "loss"}
      />
      <Stat
        label="Trades (W/L)"
        value={total > 0 ? `${winning}/${losing}` : "—"}
        mono
      />
      <Stat
        label="Win Rate"
        value={wr != null ? wr.toFixed(1) : "—"}
        unit={wr != null ? "%" : ""}
        tone={wr == null ? "default" : wr >= 50 ? "profit" : "loss"}
      />
      <Stat label="Open Positions" value={String(openCount)} />
      <Stat
        label="Open Profit"
        value={totalOpenProfit != null ? totalOpenProfit.toFixed(2) : "—"}
        unit={totalOpenProfit != null ? "USDT" : ""}
        tone={totalOpenProfit == null ? "default" : totalOpenProfit >= 0 ? "profit" : "loss"}
      />
      <Stat
        label="Balance"
        value={balanceTotal != null ? balanceTotal.toFixed(2) : "—"}
        unit={balanceTotal != null ? "USDT" : ""}
      />
      <Stat
        label="Regime"
        value={regimeName}
        tone={regimeTone}
        mono={false}
      />
      <Stat
        label="Regime Conf."
        value={regimeConf != null ? (regimeConf * 100).toFixed(0) : "—"}
        unit={regimeConf != null ? "%" : ""}
      />
    </div>
  );
}

function OpenTradesPanel({ data, error, lastUpdated, loading }) {
  const rows = Array.isArray(data) ? data.slice(0, 5) : [];
  const columns = [
    { key: "pair", label: "Pair", mono: true },
    {
      key: "side",
      label: "Side",
      render: (r) => {
        const isShort = r.is_short || r.trade_direction === "short";
        return (
          <Badge variant={isShort ? "short" : "long"} size="xs">
            {isShort ? "SHORT" : "LONG"}
          </Badge>
        );
      },
    },
    {
      key: "leverage",
      label: "Lev",
      align: "right",
      mono: true,
      render: (r) => (r.leverage ? `${r.leverage}x` : "—"),
    },
    {
      key: "profit_pct",
      label: "P&L %",
      align: "right",
      mono: true,
      render: (r) => {
        const p = r.profit_pct ?? r.profit_ratio;
        if (p == null) return "—";
        const v = p;
        const cls = v >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={cls}>
            {v >= 0 ? "+" : ""}
            {v.toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: "profit_abs",
      label: "P&L USDT",
      align: "right",
      mono: true,
      render: (r) => {
        const v = r.profit_abs;
        if (v == null) return "—";
        const cls = v >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={cls}>
            {v >= 0 ? "+" : ""}
            {v.toFixed(2)}
          </span>
        );
      },
    },
  ];

  return (
    <Card
      title="Open Positions"
      subtitle={`${Array.isArray(data) ? data.length : 0} open`}
      lastUpdated={lastUpdated}
    >
      {error ? (
        <p className="text-xs text-text-muted italic">Error: {error}</p>
      ) : (
        <Table
          columns={columns}
          rows={rows}
          loading={loading && !data}
          emptyMessage="No open positions"
        />
      )}
    </Card>
  );
}

function SystemHealthSummaryPanel({
  cronData,
  cronLastUpdated,
  sysData,
  onNavigateTab,
}) {
  const summary = safe(cronData, "summary", {});
  const overall = summary.overall || "unknown";
  const ok = summary.ok || 0;
  const stale = summary.stale || 0;

  const load = safe(sysData, "load", {});
  const disk = safe(sysData, "disk", {});
  const mem = safe(sysData, "memory", {});

  const overallVariant =
    overall === "ok" ? "ok" : overall === "warn" ? "stale" : "dead";

  return (
    <Card
      title="System Health"
      lastUpdated={cronLastUpdated}
      actions={
        <button
          onClick={() => (onNavigateTab || (() => {}))("system")}
          className="text-xxs text-accent hover:underline"
        >
          View all →
        </button>
      }
    >
      <div className="flex items-center justify-between mb-3">
        <Badge variant={overallVariant} size="sm">
          {overall.toUpperCase()}
        </Badge>
        <span className="text-xxs text-text-tertiary font-mono">
          {ok} ok · {stale} stale
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <MiniStat
          label="Load 1m"
          value={load.load_1m != null ? load.load_1m.toFixed(2) : "—"}
          sub={load.cores ? `/ ${load.cores}` : ""}
          tone={
            load.utilization_pct == null
              ? "default"
              : load.utilization_pct > 150
              ? "loss"
              : load.utilization_pct > 100
              ? "warn"
              : "default"
          }
        />
        <MiniStat
          label="Mem"
          value={mem.used_pct != null ? `${mem.used_pct.toFixed(0)}%` : "—"}
          sub={mem.used_gb != null ? `${mem.used_gb.toFixed(1)} GB` : ""}
          tone={
            mem.used_pct == null
              ? "default"
              : mem.used_pct > 90
              ? "loss"
              : mem.used_pct > 80
              ? "warn"
              : "default"
          }
        />
        <MiniStat
          label="Disk"
          value={disk.used_pct != null ? `${disk.used_pct.toFixed(0)}%` : "—"}
          sub={disk.free_gb != null ? `${disk.free_gb.toFixed(0)} GB free` : ""}
          tone={
            disk.used_pct == null
              ? "default"
              : disk.used_pct > 90
              ? "loss"
              : disk.used_pct > 80
              ? "warn"
              : "default"
          }
        />
        <MiniStat
          label="Crons"
          value={`${ok}/${(ok || 0) + (stale || 0)}`}
          sub={stale > 0 ? `${stale} stale` : "all ok"}
          tone={stale > 0 ? "warn" : "default"}
        />
      </div>
    </Card>
  );
}

function MiniStat({ label, value, sub, tone = "default" }) {
  const toneCls = {
    profit: "text-profit",
    loss: "text-loss",
    warn: "text-warn",
    default: "text-text-primary",
  }[tone];
  return (
    <div className="bg-elevated border border-border rounded px-2.5 py-2 min-w-0">
      <div className="text-xxs uppercase tracking-wider text-text-tertiary truncate">
        {label}
      </div>
      <div className={`text-lg font-mono font-semibold ${toneCls} truncate`}>
        {value}
      </div>
      {sub && (
        <div className="text-xxs text-text-muted font-mono truncate">{sub}</div>
      )}
    </div>
  );
}

function BrainPanel({ data, error, lastUpdated }) {
  const total = safe(data, "total", 0);
  const byStatus = safe(data, "by_status", {}) || {};
  const queued = byStatus.queued || 0;
  const completed = byStatus.completed || 0;
  const failed = byStatus.failed || 0;
  const running = byStatus.running || 0;
  const oldestTs = safe(data, "oldest_queued_ts");
  const oldestAgeS = oldestTs ? Date.now() / 1000 - oldestTs : null;

  return (
    <Card title="Brain" lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">Error: {error}</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MiniStat label="Total" value={total} />
          <MiniStat
            label="Queued"
            value={queued}
            sub={oldestAgeS != null ? `${formatDuration(oldestAgeS)} oldest` : ""}
            tone={queued > 0 ? "warn" : "default"}
          />
          <MiniStat label="Running" value={running} />
          <MiniStat
            label="Completed"
            value={completed}
            sub={failed > 0 ? `${failed} failed` : ""}
            tone={failed > 0 ? "warn" : "default"}
          />
        </div>
      )}
    </Card>
  );
}

function WfPanel({ data, error, lastUpdated }) {
  const available = safe(data, "available", false);
  const name = safe(data, "name", "");
  const summary = safe(data, "summary") || {};
  const agg = summary.aggregate || {};
  const passed = !!summary.pass;

  const gates = [
    { label: "WR", value: agg.weighted_win_rate, ok: agg.weighted_win_rate > 0.5, fmt: formatPct },
    { label: "Sharpe", value: agg.weighted_sharpe || agg.sharpe, ok: (agg.weighted_sharpe || agg.sharpe) > 0.5, fmt: (v) => v.toFixed(3) },
    { label: "DD", value: agg.worst_drawdown, ok: Math.abs(agg.worst_drawdown || 0) < 0.2, fmt: (v) => formatPct(Math.abs(v)) },
    { label: "PF", value: agg.weighted_profit_factor, ok: agg.weighted_profit_factor > 1.2, fmt: (v) => v.toFixed(2) },
  ];

  return (
    <Card title="Walk-Forward" lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">Error: {error}</p>
      ) : !available ? (
        <p className="text-xs text-text-muted italic">No WF runs found</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-mono text-text-secondary truncate">
                {name}
              </div>
              <div className="text-xxs text-text-tertiary">
                {summary.verdict || (passed ? "Latest run" : "Latest run")}
              </div>
            </div>
            <Badge variant={passed ? "ok" : "loss"} size="sm">
              {passed ? "PASS" : "FAIL"}
            </Badge>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {gates.map((g) => (
              <div
                key={g.label}
                className="bg-elevated border border-border rounded px-2 py-1.5 text-center"
              >
                <div className="text-xxs uppercase tracking-wider text-text-tertiary">
                  {g.label}
                </div>
                <div
                  className={`text-sm font-mono font-semibold ${
                    g.value == null
                      ? "text-text-muted"
                      : g.ok
                      ? "text-profit"
                      : "text-loss"
                  }`}
                >
                  {g.value != null ? g.fmt(g.value) : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── Tab root ───
export default function Overview({ onNavigateTab }) {
  const profit = usePolling(getProfitSummary, 15000);
  const trades = usePolling(getOpenTrades, 5000);
  const regime = usePolling(getRegimeCurrent, 60000);
  const cron = usePolling(getCronStatus, 30000);
  const sys = usePolling(getSystemHealth, 30000);
  const brain = usePolling(getBrainQueue, 30000);
  const wf = usePolling(getWfLatest, 60000);
  const balance = usePolling(getBalance, 60000);
  const dailyPerf = usePolling(() => getDailyPerformance(1), 60000);

  return (
    <div className="space-y-4">
      <StatStrip
        profit={profit.data}
        openTrades={trades.data}
        regime={regime.data}
        dailyPerf={dailyPerf.data}
        balance={balance.data}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <OpenTradesPanel
          data={trades.data}
          error={trades.error}
          lastUpdated={trades.lastUpdated}
          loading={trades.loading}
        />
        <SystemHealthSummaryPanel
          cronData={cron.data}
          cronLastUpdated={cron.lastUpdated}
          sysData={sys.data}
          onNavigateTab={onNavigateTab}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <BrainPanel
          data={brain.data}
          error={brain.error}
          lastUpdated={brain.lastUpdated}
        />
        <WfPanel data={wf.data} error={wf.error} lastUpdated={wf.lastUpdated} />
      </div>
    </div>
  );
}
