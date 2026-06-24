/**
 * StatusBadge — the module lifecycle pill shown in the nav and in every
 * ModuleShell header. Tells a user at a glance whether a module is making
 * real money, paper-trading, or still on the roadmap.
 *
 *   live → green   (running on the exchange, dry-run or real)
 *   paper → blue   (simulated, not placing orders yet)
 *   soon → gray    (coming soon — not built yet)
 *
 * Props:
 *   - status: "live" | "paper" | "soon"
 *   - size?: "xs" | "sm"
 */
const STATUS = {
  live: { label: "Live", cls: "bg-profit/10 text-profit border-profit/30", dot: "bg-profit" },
  paper: { label: "Paper", cls: "bg-accent/10 text-accent border-accent/30", dot: "bg-accent" },
  soon: { label: "Soon", cls: "bg-surface text-text-tertiary border-border", dot: "bg-text-muted" },
};

export default function StatusBadge({ status = "soon", size = "sm" }) {
  const s = STATUS[status] || STATUS.soon;
  const sizeCls =
    size === "xs" ? "text-[10px] px-1.5 py-0 leading-4" : "text-xxs px-2 py-0.5 leading-4";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border font-medium uppercase tracking-wider ${sizeCls} ${s.cls}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
