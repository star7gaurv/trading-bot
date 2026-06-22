/**
 * ParamControls — live strategy parameter sliders.
 * Edits LONG_THRESHOLD, SHORT_THRESHOLD, K_TP, K_SL via /api/params.
 * Writes to .env and restarts the container (no model reload).
 */
import { useState } from "react";
import Card from "./Card";
import { usePolling } from "../api/hooks";
import { getStrategyConfig, updateParams } from "../api/client";

const PARAM_DEFS = [
  { key: "long_threshold",  envKey: "FREQAI_LONG_THRESHOLD",  label: "Long Entry Threshold",  min: 0.1, max: 1.5, step: 0.05, desc: "Higher = fewer but more confident long entries" },
  { key: "short_threshold", envKey: "FREQAI_SHORT_THRESHOLD", label: "Short Entry Threshold", min: -1.5, max: -0.1, step: 0.05, desc: "More negative = fewer but more confident short entries" },
  { key: "k_tp",            envKey: "FREQAI_K_TP",            label: "Take-Profit (K_TP × ATR)", min: 1.0, max: 5.0, step: 0.25, desc: "ATR multiplier for trailing stop lock-in" },
  { key: "k_sl",            envKey: "FREQAI_K_SL",            label: "Stop-Loss (K_SL × ATR)",  min: 0.5, max: 3.0, step: 0.25, desc: "ATR multiplier for initial stop-loss distance" },
];

function Slider({ def, value, onChange }) {
  const pct = ((value - def.min) / (def.max - def.min)) * 100;
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <label className="text-xs text-text-secondary">{def.label}</label>
        <span className="text-xs font-mono font-semibold text-text-primary">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={def.min}
        max={def.max}
        step={def.step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none bg-surface-alt accent-accent cursor-pointer"
        style={{ background: `linear-gradient(to right, var(--accent) ${pct}%, var(--surface-alt) ${pct}%)` }}
      />
      <p className="text-xxs text-text-muted">{def.desc}</p>
    </div>
  );
}

export default function ParamControls() {
  const { data: cfg } = usePolling(getStrategyConfig, 60000);
  const envVars = cfg?.env_vars ?? {};

  const [values, setValues] = useState(null); // null = use live values
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const liveValues = {
    long_threshold:  parseFloat(envVars["FREQAI_LONG_THRESHOLD"]  ?? 0.7),
    short_threshold: parseFloat(envVars["FREQAI_SHORT_THRESHOLD"] ?? -0.6),
    k_tp:            parseFloat(envVars["FREQAI_K_TP"]            ?? 3.0),
    k_sl:            parseFloat(envVars["FREQAI_K_SL"]            ?? 2.0),
  };
  const current = values ?? liveValues;

  const hasChanges = Object.keys(current).some(
    (k) => Math.abs(current[k] - liveValues[k]) > 0.001
  );

  function handleChange(key, val) {
    setValues((prev) => ({ ...(prev ?? liveValues), [key]: val }));
    setMsg(null);
  }

  async function apply() {
    setBusy(true);
    setMsg(null);
    try {
      await updateParams(current);
      setMsg("Applied. Container restarting…");
      setValues(null);
      setConfirm(false);
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Strategy Parameters"
      subtitle="Edit entry thresholds + risk sizing — applied live without model retrain"
    >
      <div className="space-y-4">
        {PARAM_DEFS.map((def) => (
          <Slider
            key={def.key}
            def={def}
            value={current[def.key]}
            onChange={(v) => handleChange(def.key, v)}
          />
        ))}

        {hasChanges && !confirm && (
          <button
            onClick={() => setConfirm(true)}
            className="w-full py-1.5 rounded border border-accent/40 bg-accent/15 text-accent text-xs font-semibold hover:bg-accent/25 transition-colors"
          >
            Apply changes
          </button>
        )}

        {confirm && (
          <div className="border border-border rounded p-2.5 bg-elevated space-y-2">
            <p className="text-xxs text-text-secondary">
              This writes updated values to <code className="font-mono">.env</code> and restarts FreqTrade.
              No model retrain — takes ~15 seconds.
            </p>
            <div className="space-y-0.5 font-mono text-xxs text-text-muted">
              {PARAM_DEFS.filter((d) => Math.abs(current[d.key] - liveValues[d.key]) > 0.001).map((d) => (
                <div key={d.key}>
                  {d.envKey}: <span className="text-loss line-through">{liveValues[d.key].toFixed(2)}</span>
                  {" → "}<span className="text-profit">{current[d.key].toFixed(2)}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <button disabled={busy} onClick={apply}
                className="px-3 py-1 rounded text-xs bg-accent/20 text-accent border border-accent/40 hover:bg-accent/30 disabled:opacity-40">
                {busy ? "Applying…" : "Confirm"}
              </button>
              <button onClick={() => { setConfirm(false); setValues(null); }}
                className="px-3 py-1 rounded text-xs border border-border text-text-secondary hover:text-text-primary">
                Cancel
              </button>
            </div>
          </div>
        )}

        {msg && (
          <p className="text-xxs font-mono text-text-muted mt-1">{msg}</p>
        )}
      </div>
    </Card>
  );
}
