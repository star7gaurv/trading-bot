/**
 * Surface card with optional header (title, subtitle, last-updated badge, actions).
 */
import { formatRelative } from "../utils/format";

export default function Card({
  title,
  subtitle,
  lastUpdated,
  actions,
  children,
  className = "",
  dense = false,
}) {
  return (
    <section
      className={`bg-surface border border-border rounded-md shadow-soft ${className}`}
    >
      {(title || actions) && (
        <header
          className={`flex items-center justify-between gap-3 px-4 ${
            dense ? "py-2" : "py-3"
          } border-b border-border`}
        >
          <div className="min-w-0">
            {title && (
              <h2 className="text-sm font-semibold text-text-primary tracking-tight">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-xxs text-text-tertiary mt-0.5">{subtitle}</p>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {lastUpdated && (
              <span className="text-xxs text-text-muted font-mono whitespace-nowrap">
                <span className="live-dot mr-1.5" />
                {formatRelative(lastUpdated)}
              </span>
            )}
            {actions}
          </div>
        </header>
      )}
      <div className={dense ? "p-3" : "p-4"}>{children}</div>
    </section>
  );
}
