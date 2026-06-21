/**
 * TimeframeCard — switch the live trading timeframe from the UI.
 * Whole-system: a switch retrains all pairs and realigns config/.env/brain/WF.
 * Enhancements: informed switching (IC-by-TF), confirm modal, retrain progress + health,
 * rollback, audit history, data-warning banner, best-IC recommendation badge.
 */
import { useState, useMemo } from "react";
import Card from "../components/Card";
import Badge from "../components/Badge";
import { usePolling } from "../api/hooks";
import {
  getTimeframeInfo,
  switchTimeframe,
  rollbackTimeframe,
} from "../api/client";

function StatusBadge({ status }) {
  if (!status) return null;
  const st = status.state;
  if (st === "applying" || (st === "training" && !status.ready)) {
    return <Badge variant="warn" size="xs">retraining…</Badge>;
  }
  if (status.ready && status.model_present) {
    return <Badge variant="ok" size="xs">model live</Badge>;
  }
  return <Badge variant="unknown" size="xs">{st || "idle"}</Badge>;
}

/** Compute best TF (highest max |bear IC| across all features) from feature_ic_by_tf.json. */
function useBestTF(icByTf) {
  return useMemo(() => {
    if (!icByTf?.by_tf) return null;
    let best = null, bestIc = 0;
    for (const [tf, r] of Object.entries(icByTf.by_tf)) {
      const maxIc = Math.max(
        ...Object.values(r.report || {}).flatMap((w) =>
          ["bear_2025Q1", "bear_2026Q1"].map((k) => Math.abs((w[k]?.ic) ?? 0))
        ),
        0
      );
      if (maxIc > bestIc) { bestIc = maxIc; best = tf; }
    }
    return bestIc > 0.05 ? best : null;
  }, [icByTf]);
}

// IC-by-TF informed-switching panel (handles both feature_ic_by_tf.json and legacy feature_ic.json shapes).
function ICPanel({ ic, activeTf }) {
  // New format: {by_tf: {tf: {horizon, report, graduated}}}
  const tfReport = ic?.by_tf?.[activeTf] ?? (ic?.report ? ic : null);
  if (!tfReport || !tfReport.report) {
    return (
      <p className="text-xxs text-text-muted italic">
        No IC data yet — run scripts/brain/feature_ic.py --all-tf to populate.
      </p>
    );
  }
  const grad = tfReport.graduated || [];
  const rows = Object.entries(tfReport.report)
    .map(([feat, w]) => {
      const bear = ["bear_2025Q1", "bear_2026Q1"]
        .map((k) => (w[k] && w[k].ic != null ? Math.abs(w[k].ic) : 0));
      return { feat, bearMax: Math.max(...bear, 0) };
    })
    .sort((a, b) => b.bearMax - a.bearMax)
    .slice(0, 4);
  return (
    <div>
      <p className="text-xxs text-text-tertiary mb-1">
        Entry-signal strength @ {activeTf} (|bear IC|, H={tfReport.horizon ?? "?"}) — &gt;0.05 = usable
      </p>
      <div className="space-y-0.5">
        {rows.map((r) => (
          <div key={r.feat} className="flex justify-between text-xxs font-mono">
            <span className="text-text-secondary truncate mr-2">{r.feat}</span>
            <span className={r.bearMax > 0.05 ? "text-profit" : "text-text-muted"}>
              {r.bearMax.toFixed(3)}
            </span>
          </div>
        ))}
      </div>
      <p className="text-xxs text-text-muted mt-1">
        Graduated: {grad.length ? grad.join(", ") : "none"}
      </p>
    </div>
  );
}

export default function TimeframeCard() {
  // Poll every 8s so retrain progress updates while a switch is in flight.
  const { data, error, lastUpdated, refresh } = usePolling(getTimeframeInfo, 8000);
  const [pending, setPending] = useState(null); // tf awaiting confirm, or "__rollback__"
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const active = data?.active;
  const available = data?.available || [];
  const status = data?.status;
  const history = data?.history || [];
  const profiles = data?.profiles || {};
  const dataWarnings = data?.data_warnings || {};
  const bestTF = useBestTF(data?.ic_by_tf);

  async function doSwitch() {
    setBusy(true);
    setMsg(null);
    try {
      const res =
        pending === "__rollback__"
          ? await rollbackTimeframe()
          : await switchTimeframe(pending);
      setMsg(res?.note || (res?.accepted ? "Started." : res?.reason || "No change."));
      setPending(null);
      setTimeout(refresh, 1500);
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }

  const switching =
    status && (status.state === "applying" || (status.state === "training" && !status.ready));

  return (
    <Card
      title="Trading Timeframe"
      subtitle="Switching retrains all pairs (~hours) and realigns the whole system"
      lastUpdated={lastUpdated}
    >
      {error ? (
        <p className="text-xs text-text-muted italic">{error}</p>
      ) : !data ? (
        <p className="text-xs text-text-muted italic p-1">Loading…</p>
      ) : (
        <div className="space-y-3">
          {/* current + health */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-tertiary uppercase tracking-wide">Active</span>
              <span className="text-base font-mono font-semibold text-text-primary">{active}</span>
              <StatusBadge status={status} />
            </div>
            {status?.model_age_min != null && (
              <span className="text-xxs text-text-muted font-mono">
                model {status.model_age_min}m old
              </span>
            )}
          </div>

          {/* timeframe buttons */}
          <div className="flex flex-wrap gap-1.5">
            {available.map((tf) => (
              <button
                key={tf}
                disabled={busy || switching || tf === active}
                onClick={() => { setPending(tf); setMsg(null); }}
                className={`relative px-3 py-1 rounded text-xs font-mono border transition ${
                  tf === active
                    ? "bg-accent/15 text-accent border-accent/40 cursor-default"
                    : "bg-surface text-text-secondary border-border hover:border-accent/40 disabled:opacity-40"
                }`}
              >
                {tf}
                {profiles[tf]?.label_period_candles != null && (
                  <span className="text-text-muted ml-1">·lp{profiles[tf].label_period_candles}</span>
                )}
                {tf === bestTF && tf !== active && (
                  <span className="absolute -top-1.5 -right-1.5 text-profit text-[9px] font-semibold leading-none">
                    ✦
                  </span>
                )}
              </button>
            ))}
            {bestTF && (
              <span className="self-center text-xxs text-profit ml-1">
                ✦ best IC
              </span>
            )}
          </div>

          {switching && (
            <div className="text-xxs text-warn flex items-center gap-2">
              <span className="live-dot" /> Retraining {status.from}→{status.to}… model not live yet.
            </div>
          )}
          {msg && <p className="text-xxs text-text-secondary italic">{msg}</p>}

          {/* IC informed-switching */}
          <div className="border-t border-border pt-2">
            <ICPanel ic={data.ic_by_tf} activeTf={active} />
          </div>

          {/* rollback + history */}
          <div className="border-t border-border pt-2 flex items-center justify-between">
            <button
              disabled={busy || switching || history.length === 0}
              onClick={() => { setPending("__rollback__"); setMsg(null); }}
              className="text-xxs text-text-tertiary hover:text-text-secondary underline disabled:opacity-40 disabled:no-underline"
            >
              ↺ Rollback to previous
            </button>
            <span className="text-xxs text-text-muted">{history.length} change(s) logged</span>
          </div>
          {history.length > 0 && (
            <div className="space-y-0.5">
              {history.slice().reverse().slice(0, 5).map((h, i) => (
                <div key={i} className="text-xxs font-mono text-text-muted flex justify-between">
                  <span>{h.from || "—"} → {h.to}</span>
                  <span>{h.at ? new Date(h.at).toLocaleString() : ""}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* confirm modal */}
      {pending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => !busy && setPending(null)}>
          <div className="bg-surface border border-border rounded-md shadow-soft p-4 max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-text-primary mb-2">
              {pending === "__rollback__" ? "Roll back timeframe?" : `Switch to ${pending}?`}
            </h3>
            <p className="text-xxs text-text-secondary mb-2">
              This recreates the live bot, <span className="text-warn">retrains all 26 pairs (~hours)</span>,
              resets pair-regime stats, and realigns brain + walk-forward. The bot is dry-run.
            </p>
            {pending && pending !== "__rollback__" && dataWarnings[pending] && (
              <div className="mb-2 px-2 py-1.5 rounded bg-warn/10 border border-warn/30 text-xxs text-warn">
                ⚠ {dataWarnings[pending]} — data downloads via cron at 04:30 UTC.
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <button disabled={busy} onClick={() => setPending(null)}
                className="px-3 py-1 rounded text-xs border border-border text-text-secondary hover:border-accent/40 disabled:opacity-40">
                Cancel
              </button>
              <button disabled={busy} onClick={doSwitch}
                className="px-3 py-1 rounded text-xs border border-accent/40 bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-40">
                {busy ? "Starting…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
