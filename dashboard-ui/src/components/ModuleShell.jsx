import StatusBadge from "./StatusBadge";

/**
 * ModuleShell — the mandatory header every trading module wraps its content in.
 *
 * This is what makes the dashboard self-explanatory: a stranger landing on any
 * module page immediately sees (1) what it does in plain English, (2) whether
 * it's Live/Paper/Coming Soon, (3) how it makes money, and (4) the single number
 * that matters. Because the header lives here, no module can ship without it.
 *
 * Props:
 *   - name: module display name ("Directional Trading")
 *   - status: "live" | "paper" | "soon"
 *   - tagline: one plain-English sentence — what this module does
 *   - howItMakesMoney: one sentence — how the edge produces profit
 *   - hero: { label, value, unit?, tone? } — the single headline number
 *   - actions?: optional node rendered top-right (e.g. sub-tab switcher lives below)
 *   - children: the module body
 */
export default function ModuleShell({
  name,
  status = "soon",
  tagline,
  howItMakesMoney,
  hero,
  actions,
  children,
}) {
  const heroTone = {
    profit: "text-profit",
    loss: "text-loss",
    warn: "text-warn",
    default: "text-text-primary",
  }[hero?.tone || "default"];

  return (
    <div className="space-y-4">
      {/* Mandatory self-explanatory header */}
      <section className="bg-surface border border-border rounded-md shadow-soft px-5 py-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <h1 className="text-base font-semibold tracking-tight text-text-primary">{name}</h1>
              <StatusBadge status={status} />
            </div>
            {tagline && (
              <p className="text-sm text-text-secondary leading-snug max-w-xl">{tagline}</p>
            )}
            {howItMakesMoney && (
              <p className="text-xxs text-text-tertiary mt-1.5 flex items-start gap-1.5 max-w-xl">
                <span className="uppercase tracking-wider font-medium text-text-muted shrink-0">
                  How it earns
                </span>
                <span className="leading-snug">{howItMakesMoney}</span>
              </p>
            )}
          </div>

          {hero && (
            <div className="text-right shrink-0">
              <div className="text-xxs uppercase tracking-wider text-text-tertiary">{hero.label}</div>
              <div className={`text-2xl font-mono font-semibold ${heroTone}`}>
                {hero.value}
                {hero.unit && (
                  <span className="text-sm text-text-tertiary font-normal ml-1">{hero.unit}</span>
                )}
              </div>
            </div>
          )}
        </div>

        {actions && <div className="mt-3 pt-3 border-t border-border">{actions}</div>}
      </section>

      {/* Module body */}
      <div>{children}</div>
    </div>
  );
}
