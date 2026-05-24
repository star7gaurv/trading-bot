/**
 * Number, time and currency formatters.
 * Keep these tiny — no external libs.
 */

export function formatNumber(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  if (typeof n !== "number") return String(n);
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(digits) + "M";
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(digits) + "k";
  return n.toFixed(digits);
}

export function formatPct(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${(n * 100).toFixed(digits)}%`;
}

export function formatUsdt(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)} USDT`;
}

export function formatPrice(n) {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1000) return n.toFixed(2);
  if (n >= 1) return n.toFixed(4);
  if (n >= 0.01) return n.toFixed(5);
  return n.toFixed(8);
}

export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

export function formatRelative(ts) {
  if (!ts) return "";
  const diffSec = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

export function formatTime(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatDateTime(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
