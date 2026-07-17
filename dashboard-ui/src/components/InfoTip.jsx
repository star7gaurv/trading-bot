import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
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
 *
 * The popup renders through a portal into document.body, positioned via
 * getBoundingClientRect() rather than CSS position:absolute. Table headers
 * (dashboard-ui/src/components/Table.jsx) wrap in an overflow-auto scroll
 * container, which clips any absolutely-positioned child that pokes outside
 * it — z-index can't undo that clip. Portaling escapes the container entirely.
 */
export default function InfoTip({ text, label, size = 12, className = "" }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState(null);
  const wrapperRef = useRef(null);
  const buttonRef = useRef(null);
  const tooltipRef = useRef(null);

  const updatePosition = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    setCoords({ left: rect.left + rect.width / 2, top: rect.top });
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, updatePosition]);

  // Close on outside tap (touch devices where hover doesn't fire). The popup
  // is portaled outside wrapperRef's subtree, so it needs its own ref check
  // too, or a tap inside the tooltip text would incorrectly close it.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      const inWrapper = wrapperRef.current && wrapperRef.current.contains(e.target);
      const inTooltip = tooltipRef.current && tooltipRef.current.contains(e.target);
      if (!inWrapper && !inTooltip) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <span ref={wrapperRef} className={`relative inline-flex items-center gap-1 ${className}`}>
      {label && <span>{label}</span>}
      <button
        ref={buttonRef}
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
      {open && coords && createPortal(
        <span
          ref={tooltipRef}
          role="tooltip"
          style={{ position: "fixed", left: coords.left, top: coords.top - 6, transform: "translate(-50%, -100%)" }}
          className="z-50 w-max max-w-[220px]
                     rounded-md border border-border bg-elevated px-2.5 py-1.5
                     text-xxs leading-snug text-text-secondary shadow-soft whitespace-normal text-left normal-case tracking-normal"
        >
          {text}
        </span>,
        document.body
      )}
    </span>
  );
}
