/**
 * System Health tab — load/disk/memory, cron jobs with expandable log tails,
 * docker containers, watchdog status.
 */
import { useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";

import Card from "../components/Card";
import Stat from "../components/Stat";
import Table from "../components/Table";
import Badge from "../components/Badge";
import LogStream from "../components/LogStream";
import InfoTip from "../components/InfoTip";
import { usePolling } from "../api/hooks";
import { getSystemHealth, getCronStatus } from "../api/client";
import { formatRelative, formatDuration } from "../utils/format";

function safe(obj, key, fallback = null) {
  if (!obj || typeof obj !== "object") return fallback;
  const v = obj[key];
  return v == null ? fallback : v;
}

// Display-only rebrand: underlying engine is FreqTrade/FreqAI, but nothing
// on this page should surface those names — Cortexa is the product name.
function rebrand(str) {
  if (typeof str !== "string") return str;
  return str
    .replace(/freqtradeorg\/freqtrade/gi, "cortexa/cortexa-engine")
    .replace(/freqai/gi, "cortexa-brain")
    .replace(/freqtrade/gi, "Cortexa Engine");
}

// ─── Top stat strip ───
function TopStats({ sys }) {
  const load = safe(sys, "load", {});
  const mem = safe(sys, "memory", {});
  const disk = safe(sys, "disk", {});
  const ft = safe(sys, "freqtrade", {});

  const loadTone =
    load.utilization_pct == null
      ? "default"
      : load.utilization_pct > 150
      ? "loss"
      : load.utilization_pct > 100
      ? "warn"
      : "default";

  const memTone =
    mem.used_pct == null
      ? "default"
      : mem.used_pct > 90
      ? "loss"
      : mem.used_pct > 80
      ? "warn"
      : "default";

  const diskTone =
    disk.used_pct == null
      ? "default"
      : disk.used_pct > 90
      ? "loss"
      : disk.used_pct > 80
      ? "warn"
      : "default";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Stat
        label={<InfoTip label="Load 1m" text="Average number of processes waiting for CPU time over the last minute, shown against the server's core count — over 100% means the server is more loaded than it has capacity for." />}
        value={
          load.load_1m != null && load.cores != null
            ? `${load.load_1m.toFixed(2)} / ${load.cores}`
            : "—"
        }
        delta={load.utilization_pct != null ? load.utilization_pct : undefined}
        unit={load.utilization_pct != null ? "%" : ""}
        tone={loadTone}
      />
      <Stat
        label="Memory"
        value={mem.used_pct != null ? mem.used_pct.toFixed(1) : "—"}
        unit={mem.used_pct != null ? "%" : ""}
        tone={memTone}
      />
      <Stat
        label="Disk"
        value={disk.used_pct != null ? disk.used_pct.toFixed(1) : "—"}
        unit={disk.used_pct != null ? "%" : ""}
        tone={diskTone}
      />
      <Stat
        label="Cortexa"
        value={ft.running ? ft.status || "Up" : "DOWN"}
        tone={ft.running ? "profit" : "loss"}
        mono={false}
      />
    </div>
  );
}

// ─── Cron table ───
function CronRow({ job }) {
  const [expanded, setExpanded] = useState(false);
  const variant =
    job.status === "ok" ? "ok"
    : job.status === "running" ? "info"
    : job.status === "stale" ? "stale"
    : "unknown";
  const tail = Array.isArray(job.tail) ? job.tail : [];
  const lines = tail.map((t) => ({ text: t, level: "default" }));

  return (
    <>
      <tr
        onClick={() => setExpanded((v) => !v)}
        className="cursor-pointer"
      >
        <td style={{ width: 24 }}>
          {expanded ? (
            <ChevronDown size={14} className="text-text-tertiary" />
          ) : (
            <ChevronRight size={14} className="text-text-tertiary" />
          )}
        </td>
        <td>
          <Badge variant={variant} size="xs">
            {job.status}
          </Badge>
        </td>
        <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{job.name}</td>
        <td
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: "11px",
            color: "var(--text-tertiary, #888)",
          }}
        >
          {job.schedule}
        </td>
        <td
          style={{ fontFamily: "JetBrains Mono, monospace" }}
          align="right"
        >
          {job.last_run_ts ? formatRelative(job.last_run_ts * 1000) : "—"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5} style={{ padding: "8px 16px 12px" }}>
            {job.log_path ? (
              <div className="space-y-1">
                <div className="text-xxs text-text-muted font-mono truncate">
                  {job.log_path}
                </div>
                <LogStream
                  lines={lines}
                  placeholder="No recent log output"
                  maxHeight="140px"
                />
              </div>
            ) : (
              <div className="text-xxs text-text-muted italic">
                No log path detected for this cron
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function CronTable({ data, error, lastUpdated, loading }) {
  const summary = safe(data, "summary", {}) || {};
  const jobs = safe(data, "jobs", []) || [];

  // Sort: stale first, then running, then ok, then unknown
  const sorted = [...jobs].sort((a, b) => {
    const rank = { stale: 0, running: 1, ok: 2, unknown: 3 };
    return (rank[a.status] ?? 4) - (rank[b.status] ?? 4);
  });

  const running = summary.running || 0;
  const subtitle = `${jobs.length} jobs · ${summary.stale || 0} stale · ${
    running > 0 ? `${running} running · ` : ""
  }${summary.ok || 0} ok`;

  return (
    <Card title="Cron Jobs" subtitle={subtitle} lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">Error: {error}</p>
      ) : loading && !data ? (
        <div className="p-6 text-center text-text-tertiary text-xs">
          Loading…
        </div>
      ) : sorted.length === 0 ? (
        <div className="p-6 text-center text-text-tertiary text-xs">
          No cron jobs detected
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 24 }}></th>
                <th>Status</th>
                <th>Name</th>
                <th>Schedule</th>
                <th style={{ textAlign: "right" }}>Last Run</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((job, i) => (
                <CronRow key={`${job.name}-${i}`} job={job} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ─── Containers table ───
function ContainersPanel({ sys, lastUpdated }) {
  const containers = safe(sys, "containers", []) || [];
  const columns = [
    { key: "name", label: "Name", mono: true, render: (r) => rebrand(r.name) },
    {
      key: "status",
      label: "Status",
      render: (r) => {
        const up = /^Up\b/i.test(r.status || "");
        return (
          <Badge variant={up ? "ok" : "dead"} size="xs">
            {r.status || "?"}
          </Badge>
        );
      },
    },
    { key: "image", label: "Image", mono: true, render: (r) => rebrand(r.image) },
    { key: "created_at", label: "Created", mono: true },
  ];
  return (
    <Card
      title="Docker Containers"
      subtitle={`${containers.length} running`}
      lastUpdated={lastUpdated}
    >
      <Table
        columns={columns}
        rows={containers}
        emptyMessage="No containers running"
      />
    </Card>
  );
}

// ─── Watchdog ───
function WatchdogPanel({ sys }) {
  const uptime = safe(sys, "uptime_s");
  const streamer = safe(sys, "streamer", {}) || {};
  const streamerAge = streamer.uptime_s;
  return (
    <Card title="Watchdog & Processes">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-elevated border border-border rounded px-3 py-2">
          <div className="text-xxs uppercase tracking-wider text-text-tertiary">
            <InfoTip label="Threshold" text="The AI model automatically retrains on fresh market data every ~14 hours to stay current, plus a safety buffer before an alert fires if it's overdue." />
          </div>
          <div className="text-xs text-text-secondary mt-1">
            Training every 14h
            <span className="text-text-muted">
              {" "}
              (live_retrain=12h + 2h buffer)
            </span>
          </div>
        </div>
        <div className="bg-elevated border border-border rounded px-3 py-2">
          <div className="text-xxs uppercase tracking-wider text-text-tertiary">
            System Uptime
          </div>
          <div className="text-sm font-mono text-text-primary mt-1">
            {uptime != null ? formatDuration(uptime) : "—"}
          </div>
        </div>
        <div className="bg-elevated border border-border rounded px-3 py-2">
          <div className="text-xxs uppercase tracking-wider text-text-tertiary">
            Streamer Uptime
          </div>
          <div className="text-sm font-mono text-text-primary mt-1">
            {streamerAge != null ? formatDuration(streamerAge) : "—"}
            {streamer.pid != null && (
              <span className="text-text-muted text-xxs ml-2">
                pid {streamer.pid}
              </span>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ─── Tab root ───
export default function SystemHealth() {
  const sys = usePolling(getSystemHealth, 15000);
  const cron = usePolling(getCronStatus, 30000);

  return (
    <div className="space-y-4">
      <TopStats sys={sys.data} />
      <CronTable
        data={cron.data}
        error={cron.error}
        lastUpdated={cron.lastUpdated}
        loading={cron.loading}
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ContainersPanel sys={sys.data} lastUpdated={sys.lastUpdated} />
        <WatchdogPanel sys={sys.data} />
      </div>
    </div>
  );
}
