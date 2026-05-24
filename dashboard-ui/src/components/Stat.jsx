import Sparkline from "./Sparkline";
import { formatNumber } from "../utils/format";

/**
 * Dense stat block.
 * Props:
 *   - label: string
 *   - value: number | string
 *   - unit?: string (e.g. 'USDT', '%')
 *   - delta?: number (positive=green, negative=red)
 *   - sparkline?: number[] (small inline chart)
 *   - tone?: 'default' | 'profit' | 'loss' | 'warn'
 *   - mono?: boolean (force mono font on the value)
 */
export default function Stat({
  label,
  value,
  unit,
  delta,
  sparkline,
  tone = "default",
  mono = true,
}) {
  const toneColor = {
    profit: "text-profit",
    loss: "text-loss",
    warn: "text-warn",
    default: "text-text-primary",
  }[tone];

  const showValue =
    typeof value === "number" ? formatNumber(value) : value ?? "—";

  return (
    <div className="bg-surface border border-border rounded-md px-3 py-2.5 flex flex-col gap-1 min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xxs uppercase tracking-wider text-text-tertiary truncate">
          {label}
        </span>
        {delta != null && (
          <span
            className={`text-xxs font-mono ${
              delta > 0 ? "text-profit" : delta < 0 ? "text-loss" : "text-text-tertiary"
            }`}
          >
            {delta > 0 ? "+" : ""}
            {formatNumber(delta)}
            {unit === "%" ? "" : ""}
          </span>
        )}
      </div>
      <div className="flex items-baseline justify-between gap-2 min-w-0">
        <div className={`text-xl ${mono ? "font-mono" : ""} font-semibold ${toneColor} truncate`}>
          {showValue}
          {unit && (
            <span className="text-text-tertiary font-normal text-sm ml-0.5">{unit}</span>
          )}
        </div>
        {sparkline?.length > 0 && (
          <div className="w-16 h-7 shrink-0">
            <Sparkline values={sparkline} stroke={toneColor.replace("text-", "var(--")} />
          </div>
        )}
      </div>
    </div>
  );
}
