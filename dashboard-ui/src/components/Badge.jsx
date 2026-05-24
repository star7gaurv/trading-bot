/**
 * Color-coded chip. Variants: default | profit | loss | warn | info | long | short | ok | stale | dead
 */
const VARIANTS = {
  default: "bg-surface text-text-secondary border-border",
  profit: "bg-profit/10 text-profit border-profit/30",
  loss: "bg-loss/10 text-loss border-loss/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  info: "bg-accent/10 text-accent border-accent/30",
  long: "bg-profit/10 text-profit border-profit/30",
  short: "bg-loss/10 text-loss border-loss/30",
  ok: "bg-profit/10 text-profit border-profit/30",
  stale: "bg-warn/10 text-warn border-warn/30",
  dead: "bg-loss/10 text-loss border-loss/30",
  unknown: "bg-surface text-text-tertiary border-border",
};

export default function Badge({ children, variant = "default", size = "sm", className = "" }) {
  const cls = VARIANTS[variant] || VARIANTS.default;
  const sizeCls =
    size === "xs"
      ? "text-[10px] px-1.5 py-0 leading-4"
      : "text-xxs px-2 py-0.5 leading-4";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border font-medium uppercase tracking-wider ${sizeCls} ${cls} ${className}`}
    >
      {children}
    </span>
  );
}
