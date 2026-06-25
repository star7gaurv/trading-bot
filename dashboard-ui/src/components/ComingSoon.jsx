import { Lock } from "lucide-react";

/**
 * ComingSoon — locked-module placeholder body. Explains in plain English what
 * the module WILL do (sells the vision before the code exists) and optionally
 * renders a live data preview underneath the lock.
 *
 * Props:
 *   - bullets?: string[] — "what it does" plain-English points
 *   - preview?: React node — optional live data preview (scanner, etc.)
 *   - previewTitle?: string
 */
export default function ComingSoon({
  bullets = [],
  preview,
  previewTitle,
  intro = "This module is on the roadmap. Here's what it will do:",
}) {
  return (
    <div className="space-y-4">
      <section className="bg-surface border border-border rounded-md shadow-soft px-5 py-6 text-center">
        <div className="w-10 h-10 rounded-full bg-elevated border border-border flex items-center justify-center mx-auto mb-3">
          <Lock className="w-4 h-4 text-text-tertiary" />
        </div>
        <p className="text-sm text-text-secondary max-w-md mx-auto">{intro}</p>
        {bullets.length > 0 && (
          <ul className="mt-3 space-y-1.5 max-w-md mx-auto text-left">
            {bullets.map((b, i) => (
              <li key={i} className="text-xs text-text-secondary flex items-start gap-2">
                <span className="text-accent mt-0.5">•</span>
                <span className="leading-snug">{b}</span>
              </li>
            ))}
          </ul>
        )}
        <button
          disabled
          className="mt-5 px-4 py-1.5 rounded-md text-xs font-medium border border-border text-text-tertiary cursor-not-allowed"
        >
          {preview ? "Auto-trading not enabled yet" : "Notify me when live"}
        </button>
      </section>

      {preview && (
        <section className="bg-surface border border-border rounded-md shadow-soft">
          <header className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">{previewTitle || "Live preview"}</h2>
            <span className="text-xxs text-text-tertiary uppercase tracking-wider">read-only</span>
          </header>
          <div className="p-4">{preview}</div>
        </section>
      )}
    </div>
  );
}
