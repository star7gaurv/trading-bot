/**
 * FundingFarmCard — live monitor for the paper funding-rate farm.
 * Shows current APR per symbol vs the 15% entry threshold, paper positions,
 * and realized PnL — so you can see the gap to opportunity without SSH.
 *
 * The farm is correctly dormant in bear market (no symbol clears 15% APR).
 * This card makes that state visible rather than opaque.
 */
import Card from "./Card";
import Badge from "./Badge";
import { usePolling } from "../api/hooks";
import { getFundingFarm } from "../api/client";

function AprBar({ apr, threshold }) {
  const pct = Math.min(100, (Math.abs(apr) / threshold) * 100);
  const color = pct >= 100 ? "bg-profit" : pct >= 66 ? "bg-warn" : "bg-text-muted/30";
  return (
    <div className="mt-1">
      <div className="h-1.5 rounded-full bg-surface-alt overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-xxs text-text-muted mt-0.5">
        <span>{(Math.abs(apr) * 100).toFixed(1)}% APR</span>
        <span>target {(threshold * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

export default function FundingFarmCard() {
  const { data, error, lastUpdated } = usePolling(getFundingFarm, 60_000); // 1-min poll

  if (error) return null; // fail silently — don't break SystemHealth

  const threshold = data?.threshold ?? 0.15;
  const symbols = data?.symbols ?? [];
  const positions = data?.positions ?? {};
  const posCount = Object.keys(positions).length;
  const realized = data?.realized_pnl ?? 0;
  const bestApr = data?.best_apr;
  const bestSym = data?.best_symbol;

  return (
    <Card title="Funding Farm" subtitle="Paper cash-and-carry — 15% APR threshold" lastUpdated={lastUpdated}>
      {!data ? (
        <p className="text-xs text-text-muted italic">Loading…</p>
      ) : (
        <div className="space-y-3">
          {/* Summary row */}
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="text-xxs text-text-tertiary mb-0.5">Best current APR</div>
              {bestApr != null ? (
                <>
                  <span className="text-sm font-mono font-semibold text-text-primary">
                    {(Math.abs(bestApr) * 100).toFixed(2)}%
                  </span>
                  {bestSym && (
                    <span className="text-xxs text-text-muted ml-1.5">{bestSym}</span>
                  )}
                </>
              ) : (
                <span className="text-xs text-text-muted">no data</span>
              )}
            </div>
            <div className="text-right">
              <div className="text-xxs text-text-tertiary mb-0.5">Positions</div>
              <span className="text-sm font-mono font-semibold text-text-primary">{posCount}</span>
            </div>
            <div className="text-right">
              <div className="text-xxs text-text-tertiary mb-0.5">Paper P&L</div>
              <span className={`text-sm font-mono font-semibold ${realized >= 0 ? "text-profit" : "text-loss"}`}>
                {realized >= 0 ? "+" : ""}{realized.toFixed(2)} USDT
              </span>
            </div>
          </div>

          {/* Progress bar for best symbol */}
          {bestApr != null && (
            <AprBar apr={bestApr} threshold={threshold} />
          )}

          {/* Top symbols table */}
          {symbols.length > 0 && (
            <div>
              <div className="text-xxs text-text-tertiary mb-1 uppercase tracking-wide">Top symbols by |APR|</div>
              <div className="space-y-0.5">
                {symbols.slice(0, 5).map((s) => (
                  <div key={s.symbol} className="flex justify-between text-xxs font-mono">
                    <span className="text-text-secondary">{s.symbol.replace("USDT", "")}</span>
                    <div className="flex items-center gap-2">
                      <span className={Math.abs(s.apr) >= threshold ? "text-profit font-semibold" : "text-text-muted"}>
                        {(s.apr * 100).toFixed(2)}%
                      </span>
                      {s.at_threshold && <Badge variant="ok" size="xs">OPEN</Badge>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Status */}
          <div className="border-t border-border pt-2 text-xxs text-text-muted">
            {posCount === 0 ? (
              <span>
                Dormant — no symbol clears {(threshold * 100).toFixed(0)}% APR threshold.{" "}
                {bestApr != null && (
                  <span>
                    Best: {(Math.abs(bestApr) * 100).toFixed(1)}% (need{" "}
                    {((threshold - Math.abs(bestApr)) * 100).toFixed(1)}% more).
                  </span>
                )}
              </span>
            ) : (
              <span>{posCount} paper position{posCount > 1 ? "s" : ""} open.</span>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
