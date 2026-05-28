/**
 * Trades tab — open + closed history, per-pair performance, trade detail drawer.
 *
 * Three sections:
 *   1. Open trades table (force-exit button placeholder)
 *   2. Closed trades (paginated, filterable by pair / exit reason)
 *   3. Per-pair performance (WR, PF, total trades, total P&L)
 */
import { useState, useCallback } from "react";
import { X, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";

import Card from "../components/Card";
import Table from "../components/Table";
import Badge from "../components/Badge";
import { usePolling } from "../api/hooks";
import {
  getOpenTrades,
  getClosedTrades,
  getPairPerformance,
} from "../api/client";
import {
  formatPrice,
  formatRelative,
  formatDuration,
  formatDateTime,
} from "../utils/format";

// ─── helpers ───────────────────────────────────────────────────────────────

function pnlPct(t) {
  const raw = t.profit_pct ?? t.profit_ratio;
  if (raw == null) return null;
  return raw;
}

function PnlCell({ pct, abs }) {
  const cls = (pct ?? abs ?? 0) >= 0 ? "text-profit" : "text-loss";
  return (
    <span className={`font-mono ${cls}`}>
      {pct != null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%` : "—"}
      {abs != null && (
        <span className="text-text-muted ml-1 text-xxs">
          ({abs >= 0 ? "+" : ""}
          {abs.toFixed(2)})
        </span>
      )}
    </span>
  );
}

function DirectionBadge({ trade }) {
  const isShort = trade.is_short || trade.trade_direction === "short";
  return (
    <Badge variant={isShort ? "short" : "long"} size="xs">
      {isShort ? "SHORT" : "LONG"}
    </Badge>
  );
}

function ExitBadge({ reason }) {
  if (!reason) return <span className="text-text-muted">—</span>;
  const r = reason.toLowerCase();
  const variant = r.includes("stop") ? "stale" : r.includes("signal") ? "ok" : "unknown";
  return (
    <Badge variant={variant} size="xs">
      {reason.replace(/_/g, " ")}
    </Badge>
  );
}

// ─── Trade detail drawer ────────────────────────────────────────────────────

function TradeDrawer({ trade, onClose }) {
  if (!trade) return null;
  const fields = [
    ["Pair", trade.pair],
    ["Direction", trade.is_short ? "Short" : "Long"],
    ["Leverage", trade.leverage ? `${trade.leverage}×` : "—"],
    ["Stake", trade.stake_amount != null ? `${trade.stake_amount.toFixed(2)} USDT` : "—"],
    ["Open rate", formatPrice(trade.open_rate)],
    ["Close rate", formatPrice(trade.close_rate)],
    ["Current rate", formatPrice(trade.current_rate)],
    ["P&L %", pnlPct(trade) != null ? `${pnlPct(trade).toFixed(3)}%` : "—"],
    ["P&L USDT", trade.profit_abs != null ? `${trade.profit_abs.toFixed(4)} USDT` : "—"],
    ["Opened", formatDateTime(trade.open_date)],
    ["Closed", trade.close_date ? formatDateTime(trade.close_date.replace(" ", "T") + "Z") : "Open"],
    ["Duration", trade.close_date
      ? formatDuration((trade.close_timestamp - trade.open_timestamp) / 1000)
      : formatDuration((Date.now() - trade.open_timestamp) / 1000)],
    ["Exit reason", trade.exit_reason || "—"],
    ["Stop loss", trade.stop_loss_abs != null ? formatPrice(trade.stop_loss_abs) : "—"],
    ["Initial SL", trade.initial_stop_loss_abs != null ? formatPrice(trade.initial_stop_loss_abs) : "—"],
    ["Trade ID", trade.trade_id ?? trade.id ?? "—"],
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm bg-surface border-l border-border-emphasis overflow-y-auto p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-base font-mono font-semibold text-text-primary">
              {trade.pair}
            </div>
            <div className="text-xxs text-text-muted mt-0.5">
              Trade detail
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-elevated text-text-tertiary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <dl className="space-y-1">
          {fields.map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between py-1 border-b border-border gap-3"
            >
              <dt className="text-xxs text-text-tertiary uppercase tracking-wide shrink-0">
                {label}
              </dt>
              <dd className="text-xs font-mono text-text-secondary text-right truncate">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

// ─── Open trades ────────────────────────────────────────────────────────────

function OpenTradesTable({ onSelectTrade }) {
  const { data, error, loading, lastUpdated } = usePolling(getOpenTrades, 5000);
  const trades = Array.isArray(data) ? data : [];

  const columns = [
    { key: "pair", label: "Pair", mono: true },
    {
      key: "direction",
      label: "Side",
      render: (r) => <DirectionBadge trade={r} />,
    },
    {
      key: "leverage",
      label: "Lev",
      align: "right",
      mono: true,
      render: (r) => (r.leverage ? `${r.leverage}×` : "—"),
    },
    {
      key: "open_rate",
      label: "Entry",
      align: "right",
      render: (r) => (
        <span className="font-mono">{formatPrice(r.open_rate)}</span>
      ),
    },
    {
      key: "current_rate",
      label: "Current",
      align: "right",
      render: (r) => (
        <span className="font-mono">{formatPrice(r.current_rate)}</span>
      ),
    },
    {
      key: "pnl",
      label: "P&L",
      align: "right",
      render: (r) => <PnlCell pct={pnlPct(r)} abs={r.profit_abs} />,
    },
    {
      key: "duration",
      label: "Age",
      align: "right",
      mono: true,
      render: (r) =>
        formatDuration((Date.now() - r.open_timestamp) / 1000),
    },
    {
      key: "stake_amount",
      label: "Stake",
      align: "right",
      mono: true,
      render: (r) =>
        r.stake_amount != null ? `${r.stake_amount.toFixed(1)}` : "—",
    },
  ];

  return (
    <Card
      title="Open Positions"
      subtitle={`${trades.length} open`}
      lastUpdated={lastUpdated}
    >
      {error ? (
        <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
      ) : (
        <Table
          columns={columns}
          rows={trades}
          loading={loading && !data}
          emptyMessage="No open positions"
          onRowClick={onSelectTrade}
          maxHeight="320px"
        />
      )}
    </Card>
  );
}

// ─── Closed trades ──────────────────────────────────────────────────────────

const PAGE_SIZE = 25;

function ClosedTradesTable({ onSelectTrade }) {
  const [page, setPage] = useState(0);
  const [pairFilter, setPairFilter] = useState("");
  const [exitFilter, setExitFilter] = useState("");

  const fetcher = useCallback(
    () => getClosedTrades({ limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [page]
  );
  const { data, error, loading, lastUpdated, refresh } = usePolling(fetcher, 30000);

  const raw = data?.trades ?? (Array.isArray(data) ? data : []);
  const total = data?.total_trades ?? raw.length;

  // Client-side filter on loaded page
  const filtered = raw.filter((t) => {
    const pairOk = !pairFilter || t.pair?.toLowerCase().includes(pairFilter.toLowerCase());
    const exitOk = !exitFilter || (t.exit_reason ?? "").toLowerCase().includes(exitFilter.toLowerCase());
    return pairOk && exitOk;
  });

  const columns = [
    { key: "pair", label: "Pair", mono: true },
    {
      key: "direction",
      label: "Side",
      render: (r) => <DirectionBadge trade={r} />,
    },
    {
      key: "leverage",
      label: "Lev",
      align: "right",
      mono: true,
      render: (r) => (r.leverage ? `${r.leverage}×` : "—"),
    },
    {
      key: "open_rate",
      label: "Entry",
      align: "right",
      render: (r) => (
        <span className="font-mono">{formatPrice(r.open_rate)}</span>
      ),
    },
    {
      key: "close_rate",
      label: "Exit",
      align: "right",
      render: (r) => (
        <span className="font-mono">{formatPrice(r.close_rate)}</span>
      ),
    },
    {
      key: "pnl",
      label: "P&L",
      align: "right",
      render: (r) => <PnlCell pct={pnlPct(r)} abs={r.profit_abs} />,
    },
    {
      key: "exit_reason",
      label: "Exit",
      render: (r) => <ExitBadge reason={r.exit_reason} />,
    },
    {
      key: "close_date",
      label: "Closed",
      align: "right",
      mono: true,
      // FreqTrade returns "2026-05-28 03:30:00" (space, no TZ) — add T+Z so
      // all browsers parse it as UTC, not local time.
      render: (r) =>
        formatRelative(r.close_date ? r.close_date.replace(" ", "T") + "Z" : null),
    },
  ];

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Card
      title="Closed Trades"
      subtitle={`${total} total · page ${page + 1}/${pages}`}
      lastUpdated={lastUpdated}
      actions={
        <button
          onClick={refresh}
          className="p-1 rounded hover:bg-elevated text-text-tertiary hover:text-text-primary transition-colors"
          title="Refresh"
        >
          <RefreshCw size={13} />
        </button>
      }
    >
      {/* Filters */}
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Filter pair…"
          value={pairFilter}
          onChange={(e) => setPairFilter(e.target.value)}
          className="flex-1 bg-elevated border border-border rounded px-2.5 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent font-mono"
        />
        <input
          type="text"
          placeholder="Filter exit reason…"
          value={exitFilter}
          onChange={(e) => setExitFilter(e.target.value)}
          className="flex-1 bg-elevated border border-border rounded px-2.5 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
        />
      </div>

      {error ? (
        <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
      ) : (
        <>
          <Table
            columns={columns}
            rows={filtered}
            loading={loading && !data}
            emptyMessage="No closed trades"
            onRowClick={onSelectTrade}
            maxHeight="400px"
          />
          {/* Pagination */}
          <div className="flex items-center justify-between mt-3 pt-2 border-t border-border">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="flex items-center gap-1 text-xxs text-text-secondary disabled:opacity-30 hover:text-text-primary transition-colors px-2 py-1 rounded hover:bg-elevated"
            >
              <ChevronLeft size={13} /> Prev
            </button>
            <span className="text-xxs text-text-muted font-mono">
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
              disabled={page >= pages - 1}
              className="flex items-center gap-1 text-xxs text-text-secondary disabled:opacity-30 hover:text-text-primary transition-colors px-2 py-1 rounded hover:bg-elevated"
            >
              Next <ChevronRight size={13} />
            </button>
          </div>
        </>
      )}
    </Card>
  );
}

// ─── Per-pair performance ───────────────────────────────────────────────────

function PairPerformanceTable() {
  const { data, error, loading, lastUpdated } = usePolling(getPairPerformance, 60000);
  const pairs = Array.isArray(data) ? data : [];

  // Sort by total profit descending
  const sorted = [...pairs].sort((a, b) => (b.profit_all_coin ?? 0) - (a.profit_all_coin ?? 0));

  const columns = [
    { key: "key", label: "Pair", mono: true },
    {
      key: "profit_all_percent",
      label: "WR",
      align: "right",
      render: (r) => {
        const wr = r.win_ratio != null ? r.win_ratio * 100 : null;
        const cls = wr == null ? "text-text-muted" : wr >= 50 ? "text-profit" : "text-loss";
        return (
          <span className={`font-mono ${cls}`}>
            {wr != null ? `${wr.toFixed(1)}%` : "—"}
          </span>
        );
      },
    },
    {
      key: "profit_factor",
      label: "PF",
      align: "right",
      mono: true,
      render: (r) => {
        const pf = r.profit_factor;
        const cls = pf == null ? "text-text-muted" : pf >= 1.2 ? "text-profit" : pf >= 1 ? "text-warn" : "text-loss";
        return <span className={`font-mono ${cls}`}>{pf != null ? pf.toFixed(2) : "—"}</span>;
      },
    },
    {
      key: "count",
      label: "Trades",
      align: "right",
      mono: true,
    },
    {
      key: "profit_all_coin",
      label: "P&L (USDT)",
      align: "right",
      render: (r) => {
        const v = r.profit_all_coin;
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
      key: "duration_avg",
      label: "Avg dur.",
      align: "right",
      mono: true,
      render: (r) => (r.duration_avg ? formatDuration(r.duration_avg * 60) : "—"),
    },
  ];

  return (
    <Card
      title="Per-Pair Performance"
      subtitle={`${pairs.length} pairs`}
      lastUpdated={lastUpdated}
    >
      {error ? (
        <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
      ) : (
        <Table
          columns={columns}
          rows={sorted}
          loading={loading && !data}
          emptyMessage="No pair performance data"
          maxHeight="480px"
        />
      )}
    </Card>
  );
}

// ─── Tab root ────────────────────────────────────────────────────────────────

export default function Trades() {
  const [selectedTrade, setSelectedTrade] = useState(null);

  return (
    <div className="space-y-4">
      <OpenTradesTable onSelectTrade={setSelectedTrade} />
      <ClosedTradesTable onSelectTrade={setSelectedTrade} />
      <PairPerformanceTable />
      <TradeDrawer trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}
