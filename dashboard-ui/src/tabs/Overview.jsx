/**
 * Overview tab — at-a-glance dashboard.
 *
 * Rows:
 *   1. Stat strip (P&L today/closed, W/L, WR, positions, profit, balance, regime, F&G)
 *   2. Open positions + System health summary
 *   3. Exit reasons (diagnostic) + Recent closed trades
 *   4. Risk card + Brain status + Walk-forward status
 */
import React from "react";
import Card from "../components/Card";
import Stat from "../components/Stat";
import Table from "../components/Table";
import Badge from "../components/Badge";
import InfoTip from "../components/InfoTip";
import FundingFarmCard from "../components/FundingFarmCard";
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
  getExitReasons,
  getRecentTrades,
  getStrategyConfig,
  getSignalQuality,
  getTimeframeInfo,
  switchTimeframe,
} from "../api/client";
import {
  formatUsdt,
  formatNumber,
  formatPct,
  formatPrice,
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

const EXIT_REASON_LABELS = {
  exit_signal: "Signal",
  stop_loss: "Stop Loss",
  trailing_stop_loss: "Trail Stop",
  time_limit_exit: "Expired",
  roi: "ROI",
  force_sell: "Force Exit",
  force_exit: "Force Exit",
  liquidation: "Liquidation",
};

const EXIT_REASON_VARIANT = {
  exit_signal: "ok",
  trailing_stop_loss: "ok",
  roi: "ok",
  stop_loss: "dead",
  time_limit_exit: "unknown",
  force_sell: "stale",
  force_exit: "stale",
  liquidation: "dead",
};

function safe(obj, key, fallback = null) {
  if (!obj || typeof obj !== "object") return fallback;
  const v = obj[key];
  return v == null ? fallback : v;
}

function fmtDurationShort(seconds) {
  if (seconds == null || seconds < 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h === 0) return `${m}m`;
  return `${h}h ${m}m`;
}

// Compute current win/loss streak from newest-first closed trades.
// `capped` is true when the whole sampled window is one run, so the real
// streak may be longer than what we counted (shown as e.g. "30+").
function computeStreak(closed) {
  if (!Array.isArray(closed) || closed.length === 0) return null;
  const first = closed[0];
  const firstWin = (first.profit_abs ?? 0) >= 0;
  let n = 0;
  for (const t of closed) {
    const win = (t.profit_abs ?? 0) >= 0;
    if (win === firstWin) n += 1;
    else break;
  }
  return { count: n, win: firstWin, capped: n === closed.length };
}

// ─── Stat strip ───
function StatStrip({ profit, openTrades, regime, dailyPerf, balance, recentClosed }) {
  const dailyArr = Array.isArray(dailyPerf) ? dailyPerf : (dailyPerf?.data || []);
  // FreqTrade returns oldest-first — take the LAST entry for today
  const todayEntry = dailyArr.length > 0 ? dailyArr[dailyArr.length - 1] : null;
  const todayUTC = new Date().toISOString().split("T")[0];
  const isActuallyToday = todayEntry && todayEntry.date === todayUTC;
  const today = isActuallyToday ? (todayEntry.abs_profit ?? todayEntry.profit) : 0;

  const all = safe(profit, "profit_closed_coin");
  const winning = safe(profit, "winning_trades", 0) || 0;
  const losing = safe(profit, "losing_trades", 0) || 0;
  const total = winning + losing;
  const wr = total > 0 ? (winning / total) * 100 : null;

  const openArr = Array.isArray(openTrades) ? openTrades : [];
  const openCount = openArr.length;
  const totalOpenProfit = Array.isArray(openTrades)
    ? openTrades.reduce((acc, t) => acc + (t.profit_abs || 0), 0)
    : null;
  const balanceTotal = safe(balance, "total_bot") ?? safe(balance, "total");

  // Deployed %: how much of the wallet is currently tied up in open positions
  const totalStaked = openArr.reduce((acc, t) => acc + (t.stake_amount || 0), 0);
  const deployedPct = balanceTotal ? (totalStaked / balanceTotal) * 100 : null;

  // Streak + avg duration from recent closed trades
  const streak = computeStreak(recentClosed);
  const durations = (Array.isArray(recentClosed) ? recentClosed : [])
    .map((t) => t.duration_seconds)
    .filter((d) => d != null && d >= 0);
  const avgDuration = durations.length
    ? durations.reduce((a, b) => a + b, 0) / durations.length
    : null;

  const regimeName = safe(regime, "regime", "—");
  const regimeTone = REGIME_TONE[regimeName] || "default";
  const regimeConf = safe(regime, "confidence");
  const fearGreed = safe(regime, "fear_greed_value") ?? safe(regime, "fear_greed");
  const fundingRate = safe(regime, "btc_funding_rate");

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-2">
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
        label="W / L"
        value={total > 0 ? `${winning}/${losing}` : "—"}
        mono
      />
      <Stat
        label="Win Rate"
        value={wr != null ? wr.toFixed(1) : "—"}
        unit={wr != null ? "%" : ""}
        tone={wr == null ? "default" : wr >= 50 ? "profit" : "loss"}
      />
      <Stat label="Open" value={String(openCount)} />
      <Stat
        label="Open P&L"
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
        label="Streak"
        value={streak ? `${streak.count}${streak.capped ? "+" : ""}` : "—"}
        unit={streak ? (streak.win ? "wins" : "losses") : ""}
        tone={streak == null ? "default" : streak.win ? "profit" : "loss"}
        mono={false}
      />
      <Stat
        label="Deployed"
        value={deployedPct != null ? deployedPct.toFixed(0) : "—"}
        unit={deployedPct != null ? "%" : ""}
        tone={deployedPct != null && deployedPct > 80 ? "warn" : "default"}
      />
      <Stat
        label="Avg Hold"
        value={avgDuration != null ? fmtDurationShort(avgDuration) : "—"}
        mono={false}
      />
      <Stat
        label="Regime"
        value={regimeName}
        tone={regimeTone}
        mono={false}
      />
      <Stat
        label="Conf"
        value={regimeConf != null ? (regimeConf * 100).toFixed(0) : "—"}
        unit={regimeConf != null ? "%" : ""}
      />
      {fearGreed != null && (
        <Stat
          label="Fear/Greed"
          value={fearGreed}
          tone={fearGreed < 25 ? "loss" : fearGreed > 75 ? "profit" : "warn"}
        />
      )}
      {fundingRate != null && (
        <Stat
          label="Funding"
          value={(fundingRate * 100).toFixed(4)}
          unit="%"
          tone={Math.abs(fundingRate) > 0.001 ? "warn" : "default"}
          mono
        />
      )}
    </div>
  );
}

// ─── Open trades panel ───
function OpenTradesPanel({ data, error, lastUpdated, loading, walletTotal }) {
  const rows = Array.isArray(data) ? data.slice(0, 8) : [];
  const columns = [
    { key: "pair", label: "Pair", mono: true },
    {
      key: "side",
      label: "Side",
      render: (r) => {
        const isShort = r.is_short || r.trade_direction === "short";
        const lev = r.leverage && r.leverage !== 1 ? ` ${r.leverage}x` : "";
        return (
          <Badge variant={isShort ? "short" : "long"} size="xs">
            {isShort ? "SHORT" : "LONG"}{lev}
          </Badge>
        );
      },
    },
    {
      key: "wallet_pct",
      label: <InfoTip label="% Wallet" text="Share of your total balance tied up in this one position." />,
      align: "right",
      mono: true,
      render: (r) => {
        const v = r.stake_amount;
        if (v == null || !walletTotal) return "—";
        const pct = (v / walletTotal) * 100;
        const cls = pct > 25 ? "text-warn" : "text-text-muted";
        return <span className={cls}>{pct.toFixed(1)}%</span>;
      },
    },
    {
      key: "open_rate",
      label: "Entry",
      align: "right",
      mono: true,
      render: (r) => (r.open_rate != null ? formatPrice(r.open_rate) : "—"),
    },
    {
      key: "current_rate",
      label: "Now",
      align: "right",
      mono: true,
      render: (r) => (r.current_rate != null ? formatPrice(r.current_rate) : "—"),
    },
    {
      key: "profit_pct",
      label: "P&L %",
      align: "right",
      mono: true,
      render: (r) => {
        const p = r.profit_pct ?? r.profit_ratio;
        if (p == null) return "—";
        const cls = p >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={cls}>
            {p >= 0 ? "+" : ""}
            {p.toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: "profit_abs",
      label: "P&L",
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
    {
      key: "held",
      label: "Held",
      align: "right",
      mono: true,
      render: (r) => {
        const ts = r.open_timestamp;
        if (!ts) return "—";
        return fmtDurationShort((Date.now() - ts) / 1000);
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
          emptyMessage="No open positions — the bot is waiting for a strong enough signal."
        />
      )}
    </Card>
  );
}

// ─── System health summary ───
function SystemHealthSummaryPanel({ cronData, cronLastUpdated, sysData, onNavigateTab }) {
  const summary = safe(cronData, "summary", {});
  const overall = summary.overall || "unknown";
  const ok = summary.ok || 0;
  const stale = summary.stale || 0;

  const load = safe(sysData, "load", {});
  const disk = safe(sysData, "disk", {});
  const mem = safe(sysData, "memory", {});

  const overallVariant = overall === "ok" ? "ok" : overall === "warn" ? "stale" : "dead";

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
            load.utilization_pct == null ? "default"
              : load.utilization_pct > 150 ? "loss"
              : load.utilization_pct > 100 ? "warn"
              : "default"
          }
        />
        <MiniStat
          label="Mem"
          value={mem.used_pct != null ? `${mem.used_pct.toFixed(0)}%` : "—"}
          sub={mem.used_gb != null ? `${mem.used_gb.toFixed(1)} GB` : ""}
          tone={
            mem.used_pct == null ? "default"
              : mem.used_pct > 90 ? "loss"
              : mem.used_pct > 80 ? "warn"
              : "default"
          }
        />
        <MiniStat
          label="Disk"
          value={disk.used_pct != null ? `${disk.used_pct.toFixed(0)}%` : "—"}
          sub={disk.free_gb != null ? `${disk.free_gb.toFixed(0)} GB free` : ""}
          tone={
            disk.used_pct == null ? "default"
              : disk.used_pct > 90 ? "loss"
              : disk.used_pct > 80 ? "warn"
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

// ─── Exit reasons panel ───
function ExitReasonsPanel({ data, error, lastUpdated }) {
  const items = safe(data, "items", []) || [];
  const columns = [
    {
      key: "reason",
      label: "Reason",
      render: (r) => {
        const label = EXIT_REASON_LABELS[r.reason] || r.reason.replace(/_/g, " ");
        const variant = EXIT_REASON_VARIANT[r.reason] || "unknown";
        return <Badge variant={variant} size="xs">{label}</Badge>;
      },
    },
    { key: "count", label: "Count", align: "right", mono: true },
    {
      key: "wl",
      label: "W/L",
      align: "right",
      mono: true,
      render: (r) => (
        <span>
          <span className="text-profit">{r.wins}</span>
          <span className="text-text-muted">/</span>
          <span className="text-loss">{r.losses}</span>
        </span>
      ),
    },
    {
      key: "wr",
      label: "WR",
      align: "right",
      mono: true,
      render: (r) => {
        const pct = (r.wr * 100).toFixed(1);
        const cls = r.wr >= 0.5 ? "text-profit" : "text-loss";
        return <span className={cls}>{pct}%</span>;
      },
    },
    {
      key: "profit",
      label: "P&L",
      align: "right",
      mono: true,
      render: (r) => {
        const v = r.profit;
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
    <Card title="Exit Reasons" subtitle="diagnostic — why trades closed" lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">Error: {error}</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-text-muted italic">No closed trades yet</p>
      ) : (
        <Table columns={columns} rows={items.map((r, i) => ({ ...r, id: i }))} />
      )}
    </Card>
  );
}

// ─── Recent closed trades panel ───
function RecentTradesPanel({ data, error, lastUpdated }) {
  const trades = Array.isArray(data) ? data.slice(0, 6) : [];
  const columns = [
    { key: "pair", label: "Pair", mono: true },
    {
      key: "side",
      label: "Side",
      render: (r) => (
        <Badge variant={r.is_short ? "short" : "long"} size="xs">
          {r.is_short ? "SHORT" : "LONG"}
        </Badge>
      ),
    },
    {
      key: "open_rate",
      label: "Entry",
      align: "right",
      mono: true,
      render: (r) => (r.open_rate != null ? formatPrice(r.open_rate) : "—"),
    },
    {
      key: "close_rate",
      label: "Exit",
      align: "right",
      mono: true,
      render: (r) => (r.close_rate != null ? formatPrice(r.close_rate) : "—"),
    },
    {
      key: "close_reason",
      label: "Why",
      render: (r) => {
        const reason = r.close_reason || "unknown";
        const label = EXIT_REASON_LABELS[reason] || reason.replace(/_/g, " ");
        const variant = EXIT_REASON_VARIANT[reason] || "unknown";
        return <Badge variant={variant} size="xs">{label}</Badge>;
      },
    },
    {
      key: "profit_pct",
      label: "P&L %",
      align: "right",
      mono: true,
      render: (r) => {
        const p = r.profit_ratio;
        if (p == null) return "—";
        const cls = p >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={cls}>
            {p >= 0 ? "+" : ""}
            {(p * 100).toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: "profit_abs",
      label: "P&L",
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
    {
      key: "duration",
      label: "Held",
      align: "right",
      mono: true,
      render: (r) => fmtDurationShort(r.duration_seconds),
    },
  ];

  return (
    <Card title="Recent Trades" subtitle="last 6 closed" lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">Error: {error}</p>
      ) : trades.length === 0 ? (
        <p className="text-xs text-text-muted italic">No closed trades yet</p>
      ) : (
        <Table
          columns={columns}
          rows={trades.map((t) => ({ ...t, id: t.trade_id }))}
        />
      )}
    </Card>
  );
}

// ─── Risk card ───
function RiskCard({ openTrades, dailyPnl, config }) {
  const dailyLimit = parseFloat(config?.env_vars?.FREQAI_DAILY_LOSS_LIMIT || "10");
  const todayPnl = typeof dailyPnl === "number" ? dailyPnl : 0;
  const limitUsed = Math.max(0, -todayPnl);
  const limitPct = Math.min(100, (limitUsed / dailyLimit) * 100);
  const limitTone = limitPct > 80 ? "loss" : limitPct > 50 ? "warn" : "default";

  const openArr = Array.isArray(openTrades) ? openTrades : [];
  const worstOpen = openArr.reduce(
    (worst, t) => (t.profit_abs < (worst?.profit_abs ?? 0) ? t : worst),
    null
  );
  const maxSLDist = openArr.reduce((max, t) => {
    const d = t.stoploss_current_dist_ratio;
    return d != null && Math.abs(d) > max ? Math.abs(d) : max;
  }, 0);

  return (
    <Card title="Risk" subtitle="live circuit breaker + exposure">
      <div className="space-y-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xxs text-text-tertiary uppercase tracking-wider">Daily Loss Limit</span>
            <span className={`text-xs font-mono font-semibold ${limitTone === "loss" ? "text-loss" : limitTone === "warn" ? "text-warn" : "text-text-primary"}`}>
              {limitUsed.toFixed(2)} / {dailyLimit} USDT
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-elevated overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${limitPct > 80 ? "bg-loss" : limitPct > 50 ? "bg-warn" : "bg-profit"}`}
              style={{ width: `${limitPct}%` }}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <MiniStat
            label="Worst Open"
            value={worstOpen ? `${(worstOpen.profit_abs || 0).toFixed(2)}` : "—"}
            sub={worstOpen?.pair || ""}
            tone={worstOpen && worstOpen.profit_abs < 0 ? "loss" : "default"}
          />
          <MiniStat
            label="Max SL Dist"
            value={maxSLDist > 0 ? `${(maxSLDist * 100).toFixed(2)}%` : "—"}
            sub={openArr.length > 0 ? `${openArr.length} positions` : "no positions"}
            tone={maxSLDist > 0 && maxSLDist * 100 < 1 ? "warn" : "default"}
          />
        </div>
      </div>
    </Card>
  );
}

// ─── Brain panel ───
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
          <MiniStat label="Running" value={running} tone={running > 0 ? "profit" : "default"} />
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

// ─── Walk-forward panel ───
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
              <div className="text-xs font-mono text-text-secondary truncate">{name}</div>
              <div className="text-xxs text-text-tertiary">
                {summary.verdict || "Latest run"}
              </div>
            </div>
            <Badge variant={passed ? "ok" : "dead"} size="sm">
              {passed ? "PASS" : "FAIL"}
            </Badge>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {gates.map((g) => (
              <div
                key={g.label}
                className="bg-elevated border border-border rounded px-2 py-1.5 text-center"
              >
                <div className="text-xxs uppercase tracking-wider text-text-tertiary">{g.label}</div>
                <div
                  className={`text-sm font-mono font-semibold ${
                    g.value == null ? "text-text-muted" : g.ok ? "text-profit" : "text-loss"
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

// ─── Shared MiniStat ───
function MiniStat({ label, value, sub, tone = "default" }) {
  const toneCls = {
    profit: "text-profit",
    loss: "text-loss",
    warn: "text-warn",
    default: "text-text-primary",
  }[tone] || "text-text-primary";
  return (
    <div className="bg-elevated border border-border rounded px-2.5 py-2 min-w-0">
      <div className="text-xxs uppercase tracking-wider text-text-tertiary truncate">{label}</div>
      <div className={`text-lg font-mono font-semibold ${toneCls} truncate`}>{value}</div>
      {sub && <div className="text-xxs text-text-muted font-mono truncate">{sub}</div>}
    </div>
  );
}

// ─── Signal Quality card ───
function SignalQualityCard() {
  const { data, error, lastUpdated } = usePolling(getSignalQuality, 30000);
  const ratio = data?.do_predict_ratio;
  const ratioTone = ratio == null ? "default" : ratio >= 0.4 ? "profit" : ratio >= 0.2 ? "warn" : "loss";
  const ratioColor = { profit: "bg-profit", warn: "bg-warn", loss: "bg-loss", default: "bg-text-muted/40" }[ratioTone];
  return (
    <Card title="Signal Quality" subtitle={data?.timeframe ? `@${data.timeframe}` : ""} lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">Unavailable</p>
      ) : !data ? (
        <p className="text-xs text-text-muted italic">Loading…</p>
      ) : (
        <div className="space-y-2.5">
          <div>
            <div className="flex justify-between text-xxs text-text-tertiary mb-1">
              <span>do_predict ratio</span>
              <span className={`font-mono font-semibold text-${ratioTone === "profit" ? "profit" : ratioTone === "warn" ? "warn" : "loss"}`}>
                {ratio != null ? `${(ratio * 100).toFixed(0)}%` : "—"}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-alt overflow-hidden">
              <div className={`h-full rounded-full transition-all ${ratioColor}`} style={{ width: `${Math.min(100, (ratio ?? 0) * 100)}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-xxs text-text-tertiary">Longs</div>
              <div className="text-sm font-mono font-semibold text-text-primary">{data.entry_long_count ?? 0}</div>
            </div>
            <div>
              <div className="text-xxs text-text-tertiary">Shorts</div>
              <div className="text-sm font-mono font-semibold text-text-primary">{data.entry_short_count ?? 0}</div>
            </div>
            <div>
              <div className="text-xxs text-text-tertiary">Pred μ</div>
              <div className={`text-sm font-mono font-semibold ${(data.pred_mean ?? 0) >= 0 ? "text-profit" : "text-loss"}`}>
                {data.pred_mean != null ? (data.pred_mean >= 0 ? "+" : "") + data.pred_mean.toFixed(3) : "—"}
              </div>
            </div>
          </div>
          <div className="text-xxs text-text-muted">
            {data.pairs_sampled} pairs sampled · {ratio != null && ratio < 0.2 ? "⚠ Low do_predict — model may be retraining" : ratio != null && ratio >= 0.4 ? "✓ Model healthy" : "Model warming up"}
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── TF Mini-Switcher card ───
const _TF_OPTIONS = ["15m", "30m", "1h", "4h"];
function TFMiniSwitcher({ onNavigateTab }) {
  const { data, refresh } = usePolling(getTimeframeInfo, 8000);
  const [pending, setPending] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const active = data?.active;
  const status = data?.status;
  const modelAge = status?.model_age_min;
  const ageLabel = modelAge != null
    ? modelAge < 60 ? `${Math.round(modelAge)}m ago` : `${(modelAge / 60).toFixed(1)}h ago`
    : "—";
  const isTraining = status?.state === "training";

  async function doSwitch(tf) {
    setBusy(true);
    try { await switchTimeframe(tf); refresh(); }
    catch (e) { console.error(e); }
    finally { setBusy(false); setPending(null); }
  }

  return (
    <Card
      title="Timeframe"
      subtitle={isTraining ? "Retraining…" : `Model: ${ageLabel}`}
      actions={
        <button
          onClick={() => onNavigateTab?.("settings")}
          className="text-xxs text-accent hover:underline"
        >Full settings →</button>
      }
    >
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-semibold text-text-primary bg-elevated border border-border rounded px-2 py-0.5">
            {active ?? "—"}
          </span>
          {isTraining && <Badge variant="warn" size="xs">training</Badge>}
          {!isTraining && status?.ready && <Badge variant="ok" size="xs">live</Badge>}
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {_TF_OPTIONS.map((tf) => (
            <button
              key={tf}
              disabled={tf === active || busy}
              onClick={() => setPending(tf)}
              className={`text-xs font-mono px-2.5 py-1 rounded border transition-colors
                ${tf === active
                  ? "bg-accent/20 border-accent/40 text-accent cursor-default"
                  : "bg-surface-alt border-border text-text-secondary hover:border-accent hover:text-accent disabled:opacity-40"
                }`}
            >
              {tf}
            </button>
          ))}
        </div>
        {pending && (
          <div className="border border-border rounded p-2 bg-elevated text-xs space-y-1.5">
            <p className="text-text-secondary">Switch to <strong className="text-text-primary">{pending}</strong>? All 26 pairs will retrain (~hours).</p>
            <div className="flex gap-2">
              <button
                onClick={() => doSwitch(pending)}
                disabled={busy}
                className="px-2.5 py-1 bg-accent text-white rounded text-xs font-semibold hover:bg-accent/80 disabled:opacity-50"
              >Confirm</button>
              <button
                onClick={() => setPending(null)}
                className="px-2.5 py-1 border border-border rounded text-xs text-text-secondary hover:text-text-primary"
              >Cancel</button>
            </div>
          </div>
        )}
      </div>
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
  const exitReasons = usePolling(getExitReasons, 120000);
  const recentTrades = usePolling(() => getRecentTrades(30), 30000);
  const config = usePolling(getStrategyConfig, 120000);

  // Compute today's realized P&L for risk card
  const dailyArr = Array.isArray(dailyPerf.data) ? dailyPerf.data : (dailyPerf.data?.data || []);
  const todayEntry = dailyArr.length > 0 ? dailyArr[dailyArr.length - 1] : null;
  const todayUTC = new Date().toISOString().split("T")[0];
  const todayPnl = todayEntry && todayEntry.date === todayUTC
    ? (todayEntry.abs_profit ?? todayEntry.profit ?? 0)
    : 0;

  return (
    <div className="space-y-3">
      <StatStrip
        profit={profit.data}
        openTrades={trades.data}
        regime={regime.data}
        dailyPerf={dailyPerf.data}
        balance={balance.data}
        recentClosed={recentTrades.data}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <OpenTradesPanel
          data={trades.data}
          error={trades.error}
          lastUpdated={trades.lastUpdated}
          loading={trades.loading}
          walletTotal={safe(balance.data, "total_bot") ?? safe(balance.data, "total")}
        />
        <SystemHealthSummaryPanel
          cronData={cron.data}
          cronLastUpdated={cron.lastUpdated}
          sysData={sys.data}
          onNavigateTab={onNavigateTab}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <ExitReasonsPanel
          data={exitReasons.data}
          error={exitReasons.error}
          lastUpdated={exitReasons.lastUpdated}
        />
        <RecentTradesPanel
          data={recentTrades.data}
          error={recentTrades.error}
          lastUpdated={recentTrades.lastUpdated}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <RiskCard
          openTrades={trades.data}
          dailyPnl={todayPnl}
          config={config.data}
        />
        <BrainPanel
          data={brain.data}
          error={brain.error}
          lastUpdated={brain.lastUpdated}
        />
        <WfPanel data={wf.data} error={wf.error} lastUpdated={wf.lastUpdated} />
      </div>

      {/* Row 5: Funding farm + Signal quality + TF mini-switcher */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <FundingFarmCard />
        <SignalQualityCard />
        <TFMiniSwitcher onNavigateTab={onNavigateTab} />
      </div>
    </div>
  );
}
