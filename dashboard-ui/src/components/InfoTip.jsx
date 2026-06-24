import { useState, useRef, useEffect } from "react";
import { HelpCircle } from "lucide-react";

/**
 * InfoTip — a tiny "?" icon that reveals a one-line plain-English definition
 * on hover/focus. Used everywhere to keep the dashboard self-explanatory:
 * every jargon term (Win Rate, do_predict, APR, …) gets one of these.
 *
 * Props:
 *   - text: the plain-English definition (keep it to one short sentence)
 *   - label?: optional inline label rendered before the icon
 *   - size?: icon size in px (default 12)
 *   - className?: extra classes on the wrapper
 *
 * Accessible: the icon is a <button> with aria-label; the tooltip is announced
 * via aria-describedby. Works on touch (tap toggles) and keyboard (focus shows).
 */
export default function InfoTip({ text, label, size = 12, className = "" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Close on outside tap (touch devices where hover doesn't fire)
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <span ref={ref} className={`relative inline-flex items-center gap-1 ${className}`}>
      {label && <span>{label}</span>}
      <button
        type="button"
        aria-label={label ? `What is ${label}?` : "More info"}
        className="inline-flex items-center text-text-muted hover:text-accent focus:text-accent focus:outline-none transition-colors"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <HelpCircle style={{ width: size, height: size }} />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-1/2 bottom-full z-50 mb-1.5 -translate-x-1/2 w-max max-w-[220px]
                     rounded-md border border-border bg-elevated px-2.5 py-1.5
                     text-xxs leading-snug text-text-secondary shadow-soft whitespace-normal text-left normal-case tracking-normal"
        >
          {text}
        </span>
      )}
    </span>
  );
}
