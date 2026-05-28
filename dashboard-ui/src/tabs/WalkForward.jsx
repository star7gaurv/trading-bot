/**
 * Walk-Forward tab — latest run results, fold-by-fold table, history list.
 */
import { useState, useEffect } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import Card from "../components/Card";
import Badge from "../components/Badge";
import Table from "../components/Table";
import { usePolling, useFetch } from "../api/hooks";
import { getWfLatest, getWfHistory, getRunningFolds } from "../api/client";
import { formatRelative, formatDateTime } from "../utils/format";

// ─── Gate badges ─────────────────────────────────────────────────────────────

const GATES = [
  { label: "WR",     key: "weighted_win_rate",      threshold: 0.5, fmt: (v) => `${(v*100).toFixed(1)}%`, compare: (v,t) => v > t },
  { label: "Sharpe", key: "weighted_sharpe", altKey: "sharpe", threshold: 0.5, fmt: (v) => v.toFixed(3), compare: (v,t) => v > t },
  { label: "DD",     key: "worst_drawdown",          threshold: 0.2, fmt: (v) => `${(Math.abs(v)*100).toFixed(1)}%`, compare: (v,t) => Math.abs(v) < t },
  { label: "PF",     key: "weighted_profit_factor",  threshold: 1.2, fmt: (v) => v.toFixed(2), compare: (v,t) => v > t },
];

function GateRow({ agg }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {GATES.map((g) => {
        const v = agg?.[g.key] ?? agg?.[g.altKey];
        const ok = v != null && g.compare(v, g.threshold);
        const tone = v == null ? "unknown" : ok ? "ok" : "dead";
        return (
          <div
            key={g.label}
            className="bg-elevated border border-border rounded px-3 py-2 text-center"
          >
            <div className="text-xxs uppercase tracking-wider text-text-tertiary mb-1">
              {g.label}
            </div>
            <div
              className={`text-base font-mono font-semibold ${
                v == null ? "text-text-muted" : ok ? "text-profit" : "text-loss"
              }`}
            >
              {v != null ? g.fmt(v) : "—"}
            </div>
            <div className="mt-1">
              <Badge variant={tone} size="xs">
                {v == null ? "N/A" : ok ? "PASS" : "FAIL"}
              </Badge>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Latest run ───────────────────────────────────────────────────────────────

function LatestRun({ data, error, loading, lastUpdated }) {
  const [runningData, setRunningData] = useState(null);

  // Poll running folds if an active run exists
  const isRunning = !!data?.active_run_name;
  useEffect(() => {
    let timer;
    async function poll() {
      if (isRunning) {
        try {
          const res = await getRunningFolds();
          if (res && res.available) {
            setRunningData(res);
          }
        } catch (e) {
          console.error("Failed to fetch running folds", e);
        }
      } else {
        setRunningData(null);
      }
      timer = setTimeout(poll, 15000);
    }
    poll();
    return () => clearTimeout(timer);
  }, [isRunning]);

  if (loading && !data) {
    return <Card title="Latest Walk-Forward" subtitle="Loading..." />;
  }

  if (error) {
    return (
      <Card title="Latest Walk-Forward" subtitle={<span className="text-loss">Error</span>}>
        <div className="p-4 text-sm text-text-secondary">{error.message || "Failed to load"}</div>
      </Card>
    );
  }

  if (!data?.available && !isRunning) {
    return (
      <Card title="Latest Walk-Forward" subtitle="No runs found">
        <div className="p-4 text-sm text-text-secondary">Walk-forward hasn't run yet.</div>
      </Card>
    );
  }

  const renderRunCard = (runName, summary, title, badgeProps, isLive) => {
    const agg = summary?.aggregate || {};
    const tradeCount = agg.total_trades;
    const totalPnl   = agg.total_profit_abs;
    
    return (
      <Card
        key={runName}
        title={title}
        subtitle={
          <span className="flex items-center gap-2">
            <span className="font-mono text-xxs truncate max-w-xs">{runName}</span>
            {badgeProps && (
              <Badge variant={badgeProps.variant} size="xs">
                {badgeProps.text}
              </Badge>
            )}
          </span>
        }
        lastUpdated={isLive ? new Date() : lastUpdated}
      >
        <div className="space-y-4 p-4">
          {summary ? (
            <>
              <GateRow agg={agg} />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1">
                <div className="bg-elevated border border-border rounded px-3 py-2">
                  <div className="text-xxs uppercase tracking-wider text-text-tertiary">Trades</div>
                  <div className="text-base font-mono text-text-primary mt-0.5">
                    {tradeCount ?? "—"}
                  </div>
                </div>
                <div className="bg-elevated border border-border rounded px-3 py-2">
                  <div className="text-xxs uppercase tracking-wider text-text-tertiary">P&L (USDT)</div>
                  <div
                    className={`text-base font-mono mt-0.5 ${
                      totalPnl == null ? "text-text-muted" : totalPnl >= 0 ? "text-profit" : "text-loss"
                    }`}
                  >
                    {totalPnl != null ? (totalPnl >= 0 ? "+" : "") + totalPnl.toFixed(2) : "—"}
                  </div>
                </div>
                {data.target_folds != null && (
                  <div className="bg-elevated border border-border rounded px-3 py-2">
                    <div className="text-xxs uppercase tracking-wider text-text-tertiary">Folds</div>
                    <div className="text-base font-mono text-text-primary mt-0.5">
                      {data.target_folds}
                    </div>
                  </div>
                )}
              </div>
              {summary.verdict && summary.verdict.length > 0 && (
                <div className="text-xs font-mono bg-elevated border border-border rounded p-3 text-text-secondary space-y-1">
                  {summary.verdict.map((v, i) => (
                    <div key={i} className={v.includes("✅") ? "text-profit" : "text-loss"}>
                      {v}
                    </div>
                  ))}
                </div>
              )}
              <div className="pt-2">
                <FoldTable data={{summary: summary}} />
              </div>
            </>
          ) : (
            <div className="text-sm text-text-secondary">Waiting for fold metrics to become available...</div>
          )}
        </div>
      </Card>
    );
  };

  const cards = [];

  // Active run card
  if (isRunning) {
    cards.push(
      renderRunCard(
        data.active_run_name,
        runningData,
        "Active Walk-Forward (Running)",
        { variant: "warn", text: "RUNNING" },
        true
      )
    );
  }

  // Previous completed run card
  if (data.summary) {
    cards.push(
      renderRunCard(
        data.name,
        data.summary,
        isRunning ? "Last Completed Walk-Forward" : "Latest Walk-Forward",
        { variant: data.summary.pass ? "ok" : "dead", text: data.summary.pass ? "PASS" : "FAIL" },
        false
      )
    );
  }

  return <div className="space-y-4">{cards}</div>;
}

// ─── Fold metrics table ───────────────────────────────────────────────────────

function FoldTable({ data }) {
  const folds = data?.summary?.folds ?? data?.folds ?? [];

  if (!Array.isArray(folds) || folds.length === 0) {
    return (
      <Card title="Fold Metrics">
        <div className="text-xs text-text-muted italic p-4">
          {folds ? "No fold breakdown available." : "Loading…"}
        </div>
      </Card>
    );
  }

  const columns = [
    { key: "fold", label: "Fold", mono: true },
    {
      key: "train_start",
      label: "Train",
      mono: true,
      render: (r) =>
        r.train_start && r.train_end
          ? `${r.train_start.slice(0, 10)} → ${r.train_end.slice(0, 10)}`
          : "—",
    },
    {
      key: "win_rate",
      label: "WR",
      align: "right",
      render: (r) => {
        const v = r.win_rate;
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const wr = v < 1 ? v * 100 : v;
        const cls = wr >= 50 ? "text-profit" : "text-loss";
        return <span className={`font-mono ${cls}`}>{wr.toFixed(1)}%</span>;
      },
    },
    {
      key: "profit_factor",
      label: "PF",
      align: "right",
      render: (r) => {
        const v = r.profit_factor;
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const cls = v >= 1.2 ? "text-profit" : v >= 1 ? "text-warn" : "text-loss";
        return <span className={`font-mono ${cls}`}>{v.toFixed(2)}</span>;
      },
    },
    {
      key: "profit_all_coin",
      label: "P&L",
      align: "right",
      render: (r) => {
        const v = r.profit_all_coin ?? r.profit_closed_coin;
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
      key: "trade_count",
      label: "Trades",
      align: "right",
      mono: true,
      render: (r) => r.trade_count ?? r.trades ?? "—",
    },
    {
      key: "sharpe",
      label: "Sharpe",
      align: "right",
      render: (r) => {
        const v = r.weighted_sharpe ?? r.sharpe;
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const cls = v >= 0.5 ? "text-profit" : v >= 0 ? "text-warn" : "text-loss";
        return <span className={`font-mono ${cls}`}>{v.toFixed(3)}</span>;
      },
    },
  ];

  return (
    <Card title="Fold Metrics" subtitle={`${folds.length} folds`}>
      <Table columns={columns} rows={folds} emptyMessage="No folds" maxHeight="360px" />
    </Card>
  );
}

// ─── History list ─────────────────────────────────────────────────────────────

function HistoryRow({ run }) {
  const [expanded, setExpanded] = useState(false);
  // History API sends flat fields; map to aggregate-shaped object for GateRow
  const agg = run.has_summary
    ? {
        weighted_win_rate:     run.wr,
        weighted_sharpe:       run.sharpe,
        worst_drawdown:        run.dd,
        weighted_profit_factor: run.pf,
        total_trades:          run.trades,
        total_profit_abs:      run.pnl,
      }
    : {};
  const passed    = !!run.pass;
  const isRunning = run.is_active === true;
  const isStalled = !run.has_summary && !isRunning;

  const statusVariant = isRunning ? "default" : isStalled ? "warn" : passed ? "ok" : "dead";
  const statusLabel   = isRunning ? "RUNNING" : isStalled ? "STALLED" : passed ? "PASS" : "FAIL";

  return (
    <>
      <tr onClick={() => setExpanded((v) => !v)} className="cursor-pointer">
        <td style={{ width: 20 }}>
          {expanded
            ? <ChevronDown size={13} className="text-text-tertiary" />
            : <ChevronRight size={13} className="text-text-tertiary" />}
        </td>
        <td>
          <Badge variant={statusVariant} size="xs">{statusLabel}</Badge>
        </td>
        <td className="font-mono text-text-secondary truncate max-w-xs">
          {run.name}
          {isRunning && run.completed_folds != null && (
            <span className="text-xxs text-text-tertiary ml-2">
              ({run.completed_folds} folds done)
            </span>
          )}
        </td>
        <td className="font-mono text-right">
          {run.mtime ? formatRelative(run.mtime * 1000) : "—"}
        </td>
        <td className="font-mono text-right">
          {agg.total_trades ?? "—"}
        </td>
        <td className={`font-mono text-right ${
          agg.weighted_win_rate != null
            ? agg.weighted_win_rate >= 0.5 ? "text-profit" : "text-loss"
            : "text-text-muted"
        }`}>
          {agg.weighted_win_rate != null ? `${(agg.weighted_win_rate * 100).toFixed(1)}%` : "—"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="px-4 pb-3 pt-1">
            {isRunning || isStalled ? (
              <div className="text-xs text-text-muted italic py-2 text-center">
                {isRunning ? "Currently running — details will appear once completed." : "Run stalled or failed before completing."}
              </div>
            ) : (
              <GateRow agg={agg} />
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function HistoryList({ data, error, loading, lastUpdated }) {
  const runs = Array.isArray(data) ? data : (data?.items ?? []);

  return (
    <Card
      title="WF History"
      subtitle={`${runs.length} runs`}
      lastUpdated={lastUpdated}
    >
      {error ? (
        <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
      ) : loading && !data ? (
        <div className="p-6 text-center text-text-tertiary text-xs">Loading…</div>
      ) : runs.length === 0 ? (
        <div className="p-6 text-center text-text-tertiary text-xs">No runs found</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 20 }} />
                <th>Result</th>
                <th>Run ID</th>
                <th style={{ textAlign: "right" }}>Age</th>
                <th style={{ textAlign: "right" }}>Trades</th>
                <th style={{ textAlign: "right" }}>WR</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => (
                <HistoryRow key={run.name ?? i} run={run} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ─── Tab root ────────────────────────────────────────────────────────────────

export default function WalkForward() {
  const latest = usePolling(getWfLatest, 120000);
  const history = usePolling(() => getWfHistory(20), 120000);

  return (
    <div className="space-y-4">
      <LatestRun
        data={latest.data}
        error={latest.error}
        loading={latest.loading}
        lastUpdated={latest.lastUpdated}
      />
      <HistoryList
        data={history.data}
        error={history.error}
        loading={history.loading}
        lastUpdated={history.lastUpdated}
      />
    </div>
  );
}
