/**
 * ForceExitButton — per-trade manual close, with an inline confirm step.
 *
 * Used as a Table column render() in both Trades.jsx's OpenTradesTable and
 * Overview.jsx's OpenPositionsPanel, so the confirm/loading/error UX is
 * identical everywhere a human can force-close a trade — same reasoning as
 * why PnlCell.jsx was extracted rather than duplicated per-file.
 *
 * Two-tap (Close -> Confirm) since this realizes real P&L and can't be
 * undone — unlike the pause/resume toggle, which is a reversible flag flip
 * and intentionally has no confirm step.
 */
import { useState } from "react";
import { X } from "lucide-react";
import { forceExitTrade } from "../api/client";

export default function ForceExitButton({ trade, onClosed }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function doClose(e) {
    e.stopPropagation(); // don't also trigger the row's onRowClick (trade drawer)
    setBusy(true);
    setErr(null);
    try {
      const res = await forceExitTrade(trade.trade_id);
      setConfirming(false);
      onClosed?.(res);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <button
          disabled={busy}
          onClick={doClose}
          className="px-1.5 py-0.5 rounded text-xxs font-semibold bg-loss/15 text-loss border border-loss/40 hover:bg-loss/25 disabled:opacity-40"
        >
          {busy ? "Closing…" : "Confirm"}
        </button>
        <button
          disabled={busy}
          onClick={(e) => { e.stopPropagation(); setConfirming(false); setErr(null); }}
          className="p-0.5 rounded text-text-tertiary hover:text-text-primary"
        >
          <X size={12} />
        </button>
        {err && <span className="text-xxs text-loss ml-1">{err}</span>}
      </div>
    );
  }

  return (
    <button
      onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
      className="px-1.5 py-0.5 rounded text-xxs border border-border text-text-tertiary hover:border-loss/40 hover:text-loss transition-colors"
      title="Force-exit this trade now"
    >
      Close
    </button>
  );
}
