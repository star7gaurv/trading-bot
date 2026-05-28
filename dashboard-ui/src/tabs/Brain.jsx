/**
 * Brain tab — autonomous hypothesis engine status.
 *
 * Sections:
 *   1. Queue summary stat strip
 *   2. Recent experiments table (last 50, with profit/WR/Sharpe/status)
 *   3. Live brain log stream (from /ws/brain WebSocket)
 */
import { useState, useEffect, useRef } from "react";

import Card from "../components/Card";
import Stat from "../components/Stat";
import Table from "../components/Table";
import Badge from "../components/Badge";
import LogStream from "../components/LogStream";
import { usePolling } from "../api/hooks";
import { getBrainQueue, getBrainExperiments, brainLogSocket } from "../api/client";
import { formatRelative, formatDuration, formatDateTime } from "../utils/format";

// ─── Queue stat strip ────────────────────────────────────────────────────────

function QueueStrip({ data }) {
  const byStatus = data?.by_status ?? {};
  const queued = byStatus.queued ?? 0;
  const running = byStatus.running ?? 0;
  const completed = byStatus.completed ?? 0;
  const failed = byStatus.failed ?? 0;
  const scoutFailed = byStatus.scout_failed ?? 0;
  const total = data?.total ?? 0;
  const oldestTs = data?.oldest_queued_ts;
  const oldestAge = oldestTs ? (Date.now() / 1000 - oldestTs) : null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
      <Stat label="Total" value={total} />
      <Stat label="Queued" value={queued} tone={queued > 0 ? "warn" : "default"} />
      <Stat label="Running" value={running} tone={running > 0 ? "profit" : "default"} />
      <Stat label="Completed" value={completed} tone="profit" />
      <Stat label="Scout Filtered" value={scoutFailed} tone="default"
        unit="" />
      <Stat label="Failed" value={failed} tone={failed > 0 ? "loss" : "default"} />
    </div>
  );
}

// ─── Experiments table ───────────────────────────────────────────────────────

function statusVariant(status) {
  if (!status) return "unknown";
  const s = status.toLowerCase();
  if (s === "completed" || s === "done") return "ok";
  if (s === "running") return "stale";
  if (s === "failed" || s === "error") return "dead";
  if (s === "scout_failed") return "info";   // blue — filtered before full run
  return "unknown";
}

function ExperimentsTable({ data, error, loading, lastUpdated }) {
  const [windowFilter, setWindowFilter] = useState("");

  const rows = Array.isArray(data) ? data : (data?.items ?? []);

  // Enrich rows: extract window + numeric values from raw log line
  const enriched = rows.map((r) => {
    const windowMatch = r.raw?.match(/on ([\w]+):/)?.[1] ?? r.window ?? "";
    const profitRaw = r.kvs?.profit ?? "";
    const wrRaw = r.kvs?.WR ?? "";
    const profitNum = profitRaw ? parseFloat(profitRaw) : null;
    const wrNum = wrRaw ? parseFloat(wrRaw) : null;
    return { ...r, _window: windowMatch, _profit: profitNum, _wr: wrNum };
  });

  const filtered = windowFilter
    ? enriched.filter((r) =>
        r._window.toLowerCase().includes(windowFilter.toLowerCase()) ||
        (r.raw ?? "").toLowerCase().includes(windowFilter.toLowerCase())
      )
    : enriched;

  const columns = [
    {
      key: "verdict",
      label: "Result",
      render: (r) => (
        <Badge variant={statusVariant(r.verdict)} size="xs">
          {r.verdict ?? "—"}
        </Badge>
      ),
    },
    { key: "_window", label: "Window", mono: true },
    {
      key: "_profit",
      label: "Profit %",
      align: "right",
      render: (r) => {
        const v = r._profit;
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const cls = v >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={`font-mono ${cls}`}>
            {v >= 0 ? "+" : ""}{v.toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: "_wr",
      label: "WR",
      align: "right",
      render: (r) => {
        const v = r._wr;
        if (v == null) return <span className="text-text-muted font-mono">—</span>;
        const cls = v >= 50 ? "text-profit" : "text-loss";
        return <span className={`font-mono ${cls}`}>{v.toFixed(1)}%</span>;
      },
    },
    { key: "version", label: "Ver", mono: true },
    { key: "hypothesis_id", label: "ID", mono: true },
    {
      key: "ts",
      label: "Time",
      align: "right",
      mono: true,
      render: (r) => (r.ts ? formatRelative(new Date(r.ts).getTime()) : "—"),
    },
  ];

  return (
    <Card
      title="Recent Experiments"
      subtitle={`${rows.length} results`}
      lastUpdated={lastUpdated}
    >
      <div className="mb-2 px-1 text-xxs text-text-muted leading-relaxed">
        <span className="text-text-tertiary font-semibold">How it works: </span>
        Each experiment runs a cheap <span className="font-mono text-accent">SCOUT</span> on 6 pairs first (~15 min).
        If profit &gt; 0, Sharpe &gt; 0, trades ≥ 2 → <span className="font-mono text-profit">full run</span> on all 26 pairs (~60 min) → Telegram notification.
        <span className="font-mono text-info"> SCOUT_FAILED</span> = filtered silently (no Telegram). Only full runs send notifications.
      </div>
      <div className="mb-3">
        <input
          type="text"
          placeholder="Filter by window (e.g. bear_2025Q1)…"
          value={windowFilter}
          onChange={(e) => setWindowFilter(e.target.value)}
          className="w-full bg-elevated border border-border rounded px-2.5 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent font-mono"
        />
      </div>
      {error ? (
        <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
      ) : (
        <Table
          columns={columns}
          rows={filtered}
          loading={loading && !data}
          emptyMessage="No experiments yet"
          maxHeight="400px"
        />
      )}
    </Card>
  );
}

// ─── Brain log stream (live WebSocket) ──────────────────────────────────────

const MAX_LOG_LINES = 500;

function levelOf(text) {
  const t = (text || "").toLowerCase();
  if (t.includes("error") || t.includes("fail") || t.includes("exception")) return "error";
  if (t.includes("warn")) return "warn";
  if (t.includes("pass") || t.includes("promot") || t.includes("success")) return "ok";
  return "info";
}

function BrainLogStream() {
  const [lines, setLines] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    let ws;
    let unmounted = false;

    function connect() {
      if (unmounted) return;
      try {
        ws = brainLogSocket();
        wsRef.current = ws;
      } catch {
        return;
      }

      ws.onopen = () => !unmounted && setConnected(true);
      ws.onclose = () => {
        if (!unmounted) {
          setConnected(false);
          // Reconnect after 3s
          setTimeout(connect, 3000);
        }
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        if (unmounted) return;
        try {
          const payload = JSON.parse(ev.data);
          const text =
            typeof payload === "string"
              ? payload
              : payload.message ?? payload.text ?? JSON.stringify(payload);
          setLines((prev) => {
            const next = [...prev, { text, level: levelOf(text) }];
            return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
          });
        } catch {
          setLines((prev) => {
            const next = [...prev, { text: ev.data, level: "info" }];
            return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
          });
        }
      };
    }

    connect();

    return () => {
      unmounted = true;
      ws?.close();
    };
  }, []);

  return (
    <Card
      title="Brain Log Stream"
      subtitle={
        connected ? (
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-profit animate-pulse inline-block" />
            Live
          </span>
        ) : (
          <span className="text-warn">Reconnecting…</span>
        )
      }
    >
      <LogStream
        lines={lines}
        placeholder="Waiting for brain log events…"
        showFilter
        maxHeight="480px"
      />
    </Card>
  );
}

// ─── Tab root ────────────────────────────────────────────────────────────────

export default function Brain() {
  const queue = usePolling(getBrainQueue, 30000);
  const experiments = usePolling(() => getBrainExperiments(50), 30000);

  return (
    <div className="space-y-4">
      <QueueStrip data={queue.data} />
      <ExperimentsTable
        data={experiments.data}
        error={experiments.error}
        loading={experiments.loading}
        lastUpdated={experiments.lastUpdated}
      />
      <BrainLogStream />
    </div>
  );
}
