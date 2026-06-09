/**
 * Signals tab — Live Signal Monitor.
 *
 * For every whitelisted pair, shows the current entry signal and the EXACT reason
 * it is / isn't entering — answering "why no trades?" at a glance instead of
 * digging through logs. The blocker reason is computed server-side by elimination,
 * replicating the strategy's gate order, so it is authoritative.
 */
import { useMemo, useState } from "react";

import Card from "../components/Card";
import Table from "../components/Table";
import Badge from "../components/Badge";
import Stat from "../components/Stat";
import { usePolling } from "../api/hooks";
import { getSignals } from "../api/client";

// status code → { label, variant, tone }
const STATUS_META = {
  enter:      { label: "ENTER",        variant: "ok" },
  threshold:  { label: "below thresh", variant: "unknown" },
  ta_ema:     { label: "EMA-50 trend", variant: "stale" },
  ta_rsi:     { label: "RSI extreme",  variant: "stale" },
  ta_bb:      { label: "at BB band",   variant: "stale" },
  regime:     { label: "regime block", variant: "stale" },
  gated:      { label: "pair gated",   variant: "dead" },
  no_predict: { label: "no predict",   variant: "dead" },
};

function StatusBadge({ code }) {
  const meta = STATUS_META[code] || { label: code || "—", variant: "unknown" };
  return <Badge variant={meta.variant} size="xs">{meta.label}</Badge>;
}

const REGIME_TONE = {
  BULL: "profit", EUPHORIA: "profit", NEUTRAL: "warn", BEAR: "loss", CRASH: "loss",
};

function fmtNum(v, d = 3) {
  return v == null ? "—" : Number(v).toFixed(d);
}

export default function Signals() {
  const { data, error, loading, lastUpdated } = usePolling(getSignals, 20000);
  const [hideGated, setHideGated] = useState(false);

  const rows = useMemo(() => {
    const arr = data?.pairs ?? [];
    return hideGated ? arr.filter((r) => !r.gated) : arr;
  }, [data, hideGated]);

  const entering = data?.entering_count ?? 0;
  const total = data?.count ?? 0;

  // Aggregate the dominant blocker so the user sees WHY the book is quiet
  const blockerSummary = useMemo(() => {
    const counts = {};
    for (const r of data?.pairs ?? []) {
      if (r.entering) continue;
      // the "closest to firing" side is whichever isn't a hard block; prefer the
      // less-severe of the two statuses for the summary
      const codes = [r.long_status, r.short_status];
      const pick = codes.includes("threshold") ? "threshold"
        : codes.find((c) => c.startsWith("ta_")) ? "ta"
        : codes.includes("regime") ? "regime"
        : codes.includes("gated") ? "gated"
        : codes.includes("no_predict") ? "no_predict" : "other";
      counts[pick] = (counts[pick] || 0) + 1;
    }
    return counts;
  }, [data]);

  const columns = [
    { key: "pair", label: "Pair", mono: true,
      render: (r) => (r.pair || "").replace("/USDT:USDT", "").replace("/USDT", "") },
    {
      key: "regime", label: "Regime",
      render: (r) => (
        <Badge variant="unknown" size="xs">
          <span className={
            REGIME_TONE[r.regime] === "profit" ? "text-profit"
            : REGIME_TONE[r.regime] === "loss" ? "text-loss"
            : REGIME_TONE[r.regime] === "warn" ? "text-warn" : ""
          }>{r.regime}</span>
        </Badge>
      ),
    },
    {
      key: "do_predict", label: "Predict", align: "center",
      render: (r) => r.do_predict === 1
        ? <span className="text-profit font-mono">✓</span>
        : <span className="text-loss font-mono" title="model not predicting (outlier/warmup)">✗</span>,
    },
    { key: "long_status", label: "Long", render: (r) => <StatusBadge code={r.long_status} /> },
    { key: "short_status", label: "Short", render: (r) => <StatusBadge code={r.short_status} /> },
    {
      key: "pred", label: "Pred", align: "right", mono: true,
      render: (r) => {
        const v = r.pred;
        if (v == null) return "—";
        const cls = v >= 0 ? "text-profit" : "text-loss";
        return <span className={cls}>{v >= 0 ? "+" : ""}{fmtNum(v, 2)}</span>;
      },
    },
    {
      key: "thr", label: "L / S thr", align: "right", mono: true,
      render: (r) => (
        <span className="text-text-muted text-xxs">
          {fmtNum(r.long_threshold, 2)} / {fmtNum(r.short_threshold, 2)}
        </span>
      ),
    },
    {
      key: "rsi_14", label: "RSI", align: "right", mono: true,
      render: (r) => {
        const v = r.rsi_14;
        if (v == null) return "—";
        const cls = v >= 68 ? "text-loss" : v <= 32 ? "text-profit" : "text-text-secondary";
        return <span className={cls}>{v.toFixed(0)}</span>;
      },
    },
  ];

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Entering Now"
          value={`${entering}`}
          unit={total ? `/ ${total}` : ""}
          tone={entering > 0 ? "profit" : "warn"}
        />
        <Stat label="Below Threshold" value={blockerSummary.threshold || 0}
          tone="default" />
        <Stat label="TA-Blocked" value={blockerSummary.ta || 0} tone="default" />
        <Stat label="Gated / No-Predict"
          value={(blockerSummary.gated || 0) + (blockerSummary.no_predict || 0)}
          tone={(blockerSummary.gated || 0) + (blockerSummary.no_predict || 0) > 0 ? "loss" : "default"} />
      </div>

      <Card
        title="Live Signal Monitor"
        subtitle={`${total} pairs · ${entering} entering`}
        lastUpdated={lastUpdated}
        actions={
          <label className="flex items-center gap-1.5 text-xxs text-text-tertiary cursor-pointer">
            <input type="checkbox" checked={hideGated}
              onChange={(e) => setHideGated(e.target.checked)} />
            Hide gated
          </label>
        }
      >
        <div className="mb-2 px-1 text-xxs text-text-muted leading-relaxed">
          Per-pair entry status from the last closed 15m candle. The Long/Short
          column shows the exact gate blocking entry (in the strategy's check order):
          <span className="font-mono text-info"> below thresh</span> = model signal too weak ·
          <span className="font-mono"> EMA-50/RSI/BB</span> = TA filter ·
          <span className="font-mono"> regime</span> = regime hard-block ·
          <span className="font-mono text-loss"> gated</span> = pair-regime gate ·
          <span className="font-mono text-loss"> no predict</span> = model not scoring this candle.
        </div>
        {error ? (
          <p className="text-xs text-text-muted italic px-1">Error: {error}</p>
        ) : (
          <Table
            columns={columns}
            rows={rows.map((r) => ({ ...r, id: r.pair }))}
            loading={loading && !data}
            emptyMessage="No signal data"
            maxHeight="600px"
          />
        )}
      </Card>
    </div>
  );
}
