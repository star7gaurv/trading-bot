/**
 * Walk-Forward tab — latest run results, fold-by-fold table, history list.
 */
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import Card from "../components/Card";
import Badge from "../components/Badge";
import Table from "../components/Table";
import { usePolling, useFetch } from "../api/hooks";
import { getWfLatest, getWfHistory } from "../api/client";
import { formatRelative, formatDateTime } from "../utils/format";

// ─── Gate badges ─────────────────────────────────────────────────────────────

const GATES = [
  { label: "WR", key: "win_rate", threshold: 0.5, fmt: (v) => `${(v * 100).toFixed(1)}%`, compare: (v, t) => v > t },
  { label: "Sharpe", key: "weighted_sharpe", altKey: "sharpe", threshold: 0.5, fmt: (v) => v.toFixed(3), compare: (v, t) => v > t },
  { label: "DD", key: "max_drawdown", threshold: 0.2, fmt: (v) => `${(Math.abs(v) * 100).toFixed(1)}%`, compare: (v, t) => Math.abs(v) < t },
  { label: "PF", key: "profit_factor", threshold: 1.2, fmt: (v) => v.toFixed(2), compare: (v, t) => v > t },
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
  if (loading && !data) {
    return (
      <Card title="Latest Walk-Forward">
        <div className="text-xs text-text-muted italic p-4">Loading…</div>
      </Card>
    );
  }

  if (error || !data?.available) {
    return (
      <Card title="Latest Walk-Forward" lastUpdated={lastUpdated}>
        <div className="text-xs text-text-muted italic p-4">
          {error ?? "No WF runs found yet."}
        </div>
      </Card>
    );
  }

  const summary = data.summary ?? {};
  const agg = summary.aggregate ?? summary.summary ?? {};
  const passed = !!summary.pass;
  const name = data.name ?? "";

  // Additional fields
  const tradeCount = agg.trade_count ?? agg.trades;
  const totalPnl = agg.profit_all_coin ?? agg.profit_closed_coin;
  const folds = agg.folds ?? summary.fold_count;

  return (
    <Card
      title="Latest Walk-Forward"
      subtitle={
        <span className="flex items-center gap-2">
          <span className="font-mono text-xxs truncate max-w-xs">{name}</span>
          <Badge variant={passed ? "ok" : "dead"} size="xs">
            {passed ? "PASS" : "FAIL"}
          </Badge>
        </span>
      }
      lastUpdated={lastUpdated}
    >
      <div className="space-y-4">
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
              {totalPnl != null ? `${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}` : "—"}
            </div>
          </div>
          <div className="bg-elevated border border-border rounded px-3 py-2">
            <div className="text-xxs uppercase tracking-wider text-text-tertiary">Folds</div>
            <div className="text-base font-mono text-text-primary mt-0.5">{folds ?? "—"}</div>
          </div>
          <div className="bg-elevated border border-border rounded px-3 py-2">
            <div className="text-xxs uppercase tracking-wider text-text-tertiary">Verdict</div>
            <div className={`text-sm font-mono mt-0.5 ${passed ? "text-profit" : "text-loss"}`}>
              {summary.verdict || (passed ? "All gates pass" : "Gate failed")}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
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
  const agg = run.summary?.aggregate ?? run.summary ?? {};
  const passed = !!run.summary?.pass;

  return (
    <>
      <tr onClick={() => setExpanded((v) => !v)} className="cursor-pointer">
        <td style={{ width: 20 }}>
          {expanded ? (
            <ChevronDown size={13} className="text-text-tertiary" />
          ) : (
            <ChevronRight size={13} className="text-text-tertiary" />
          )}
        </td>
        <td>
          <Badge variant={passed ? "ok" : "dead"} size="xs">
            {passed ? "PASS" : "FAIL"}
          </Badge>
        </td>
        <td className="font-mono text-text-secondary truncate max-w-xs">{run.name}</td>
        <td className="font-mono text-right">
          {run.mtime ? formatRelative(run.mtime * 1000) : "—"}
        </td>
        <td className="font-mono text-right">
          {agg.trade_count ?? agg.trades ?? "—"}
        </td>
        <td
          className={`font-mono text-right ${
            agg.win_rate != null
              ? agg.win_rate >= 0.5
                ? "text-profit"
                : "text-loss"
              : "text-text-muted"
          }`}
        >
          {agg.win_rate != null ? `${(agg.win_rate * 100).toFixed(1)}%` : "—"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="px-4 pb-3 pt-1">
            <div className="grid grid-cols-4 gap-2">
              <GateRow agg={agg} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function HistoryList({ data, error, loading, lastUpdated }) {
  const runs = Array.isArray(data) ? data : [];

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
      <FoldTable data={latest.data} />
      <HistoryList
        data={history.data}
        error={history.error}
        loading={history.loading}
        lastUpdated={history.lastUpdated}
      />
    </div>
  );
}
