/**
 * SubTabs — pill-style switcher for navigating WITHIN a module
 * (e.g. Directional → Dashboard / Trades / Performance / Signals).
 * Distinct from the top-level Tab bar so users don't confuse module
 * navigation with module-internal navigation.
 *
 * Props:
 *   - tabs: [{ id, label }]
 *   - active: string
 *   - onChange: (id) => void
 */
export default function SubTabs({ tabs, active, onChange }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {tabs.map((t) => {
        const isActive = t.id === active;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition whitespace-nowrap
              ${
                isActive
                  ? "bg-accent/15 text-accent border border-accent/30"
                  : "text-text-tertiary hover:text-text-secondary border border-transparent hover:bg-hover"
              }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
