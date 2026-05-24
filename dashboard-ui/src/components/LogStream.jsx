import { useEffect, useRef, useState } from "react";

/**
 * Virtualized-ish log feed. Auto-scrolls to bottom unless user scrolled up.
 * Props:
 *   lines: array of { text: string, level?: 'info'|'ok'|'warn'|'error' }
 *   placeholder?: string
 *   showFilter?: boolean
 *   maxHeight?: string
 */
const LEVEL_STYLES = {
  ok: "text-profit",
  info: "text-text-secondary",
  warn: "text-warn",
  error: "text-loss",
  default: "text-text-tertiary",
};

export default function LogStream({
  lines = [],
  placeholder = "Awaiting log stream…",
  showFilter = false,
  maxHeight = "400px",
}) {
  const [filter, setFilter] = useState("");
  const ref = useRef(null);
  const stickToBottom = useRef(true);

  // Track if user scrolled away from bottom
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickToBottom.current = dist < 20;
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll when new lines arrive (if still at bottom)
  useEffect(() => {
    const el = ref.current;
    if (!el || !stickToBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [lines]);

  const filtered = filter
    ? lines.filter((l) =>
        (l.text || "").toLowerCase().includes(filter.toLowerCase())
      )
    : lines;

  return (
    <div className="flex flex-col">
      {showFilter && (
        <div className="mb-2 flex items-center gap-2">
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter…"
            className="flex-1 text-xs"
          />
          <span className="text-xxs text-text-tertiary font-mono whitespace-nowrap">
            {filtered.length} / {lines.length}
          </span>
        </div>
      )}
      <div
        ref={ref}
        className="bg-canvas border border-border rounded font-mono text-[11px] leading-[18px] overflow-y-auto"
        style={{ maxHeight }}
      >
        {filtered.length === 0 ? (
          <div className="p-4 text-text-muted">{placeholder}</div>
        ) : (
          <div className="px-3 py-2">
            {filtered.map((line, i) => {
              const level = line.level || "default";
              return (
                <div
                  key={i}
                  className={`whitespace-pre-wrap break-all ${LEVEL_STYLES[level] || LEVEL_STYLES.default}`}
                >
                  {line.text}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
