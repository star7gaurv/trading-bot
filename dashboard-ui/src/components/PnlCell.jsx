/**
 * Shared P&L cell — combines percent + absolute USDT into one column
 * (e.g. "+0.43% (+0.35)") instead of two separate columns. Extracted from
 * Trades.jsx so Overview.jsx's Open Positions / Recent Trades panels render
 * P&L the same way as the Trades tab.
 */

// profit_pct is already percentage-scaled (e.g. 0.43 = 0.43%); profit_ratio
// fallback is assumed pre-scaled the same way by callers that use it directly.
// Callers whose own field is a raw fraction (e.g. 0.0043) must scale it
// themselves before passing `pct` to PnlCell.
export function pnlPct(t) {
  const raw = t.profit_pct ?? t.profit_ratio;
  if (raw == null) return null;
  return raw;
}

export default function PnlCell({ pct, abs }) {
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
