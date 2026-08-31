import { Activity, LogOut } from "lucide-react";
import Tab from "./Tab";
import StatusBadge from "./StatusBadge";
import { logout } from "../api/client";

/**
 * Top-level layout: sticky header + tab bar + content area.
 * Props:
 *   - tabs: [{ id, label, icon?, badge? }]
 *   - activeTab: string
 *   - onTabChange: (id) => void
 *   - children: React node (the active tab's content)
 *   - globalStatus: { color: 'profit'|'warn'|'loss', label: string }
 */
export default function Layout({ tabs, activeTab, onTabChange, children, globalStatus }) {
  const status = globalStatus || { color: "profit", label: "System Online" };
  const statusColor = {
    profit: "text-profit border-profit/30 bg-profit/5",
    warn: "text-warn border-warn/30 bg-warn/5",
    loss: "text-loss border-loss/30 bg-loss/5",
  }[status.color] || "text-text-secondary border-border bg-surface";

  const handleLogout = () => {
    logout();
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-canvas/95 backdrop-blur supports-[backdrop-filter]:bg-canvas/85">
        <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded bg-accent/10 border border-accent/30 flex items-center justify-center">
              <Activity className="w-4 h-4 text-accent" />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">
                Cortexa <span className="text-text-tertiary font-normal">· Console</span>
              </div>
              <div className="text-[11px] text-text-tertiary font-mono">v2 · {new Date().toISOString().slice(0, 10)}</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-2.5 py-1 rounded text-xxs font-medium border ${statusColor}`}>
              <span className={`live-dot ${status.color === "warn" ? "stale" : status.color === "loss" ? "dead" : ""}`}></span>
              <span className="uppercase tracking-wider">{status.label}</span>
            </div>
            <button
              onClick={handleLogout}
              className="text-xxs text-text-tertiary hover:text-text-primary flex items-center gap-1.5 px-2 py-1 rounded hover:bg-hover transition"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>

        {/* Grouped tab bar — "Modules" (products) vs "System" (engine room) */}
        <nav className="max-w-[1400px] mx-auto px-6">
          <div className="flex items-center gap-1 overflow-x-auto -mb-px">
            {tabs.map((t, i) => {
              const prev = tabs[i - 1];
              const newGroup = t.group && t.group !== prev?.group;
              return (
                <div key={t.id} className="flex items-center">
                  {newGroup && (
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wider text-text-muted whitespace-nowrap select-none
                        ${i === 0 ? "pr-3" : "pl-4 pr-3 ml-2 border-l border-border"}`}
                    >
                      {t.group}
                    </span>
                  )}
                  <Tab
                    label={t.label}
                    icon={t.icon}
                    badge={t.badge}
                    statusBadge={t.status ? <StatusBadge status={t.status} size="xs" /> : null}
                    active={t.id === activeTab}
                    onClick={() => onTabChange(t.id)}
                  />
                </div>
              );
            })}
          </div>
        </nav>
      </header>

      {/* Content */}
      <main className="max-w-[1400px] mx-auto px-6 py-6">{children}</main>

      {/* Footer */}
      <footer className="max-w-[1400px] mx-auto px-6 py-6 border-t border-border mt-12 text-xxs text-text-muted flex justify-between">
        <span>Cortexa autonomous trading brain · ARM64</span>
        <span className="font-mono">{new Date().toLocaleString()}</span>
      </footer>
    </div>
  );
}
