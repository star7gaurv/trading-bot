/**
 * Individual tab button. Active tab gets an underline + accent color.
 */
export default function Tab({ label, icon: Icon, badge, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`relative flex items-center gap-2 px-4 h-11 text-sm font-medium transition whitespace-nowrap
        ${
          active
            ? "text-text-primary"
            : "text-text-tertiary hover:text-text-secondary"
        }`}
    >
      {Icon && <Icon className="w-3.5 h-3.5" />}
      <span>{label}</span>
      {badge != null && (
        <span
          className={`text-[10px] font-semibold rounded px-1.5 py-0.5 ml-0.5
          ${
            active
              ? "bg-accent/15 text-accent"
              : "bg-surface text-text-tertiary border border-border"
          }`}
        >
          {badge}
        </span>
      )}
      {active && (
        <span className="absolute left-0 right-0 bottom-0 h-0.5 bg-accent rounded-t-sm" />
      )}
    </button>
  );
}
