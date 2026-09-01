/**
 * Settings tab — read-only view of live config, env vars, pair whitelist,
 * FreqAI identifier, and thresholds.
 */
import Card from "../components/Card";
import Badge from "../components/Badge";
import { usePolling } from "../api/hooks";
import { getStrategyConfig, getWhitelist, getBalance } from "../api/client";
import TimeframeCard from "./TimeframeCard";
import ParamControls from "../components/ParamControls";

// ─── helpers ────────────────────────────────────────────────────────────────

function displayStrategyName(raw) {
  if (typeof raw !== "string") return raw;
  return raw.replace(/finbuddy/gi, "Cortexa");
}

function KV({ label, value, mono = true, tone }) {
  const toneClass =
    tone === "profit"
      ? "text-profit"
      : tone === "loss"
      ? "text-loss"
      : tone === "warn"
      ? "text-warn"
      : "text-text-secondary";

  return (
    <div className="flex items-start justify-between py-1.5 border-b border-border gap-4 last:border-0">
      <dt className="text-xxs text-text-tertiary uppercase tracking-wide shrink-0 pt-0.5">
        {label}
      </dt>
      <dd
        className={`text-xs ${mono ? "font-mono" : ""} ${toneClass} text-right break-all max-w-xs`}
      >
        {value ?? "—"}
      </dd>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <Card title={title}>
      <dl className="space-y-0">{children}</dl>
    </Card>
  );
}

// ─── Whitelist display ───────────────────────────────────────────────────────

function WhitelistPanel({ data, loading, error, lastUpdated }) {
  const pairs = Array.isArray(data) ? data : data?.whitelist ?? [];

  return (
    <Card
      title="Pair Whitelist"
      subtitle={`${pairs.length} pairs`}
      lastUpdated={lastUpdated}
    >
      {error ? (
        <p className="text-xs text-text-muted italic">{error}</p>
      ) : loading && !data ? (
        <div className="text-xs text-text-muted italic p-2">Loading…</div>
      ) : (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {pairs.map((p) => (
            <Badge key={p} variant="unknown" size="xs">
              {p.replace("/USDT:USDT", "").replace("/USDT", "")}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  );
}

// ─── Balance ─────────────────────────────────────────────────────────────────

function BalancePanel({ data, loading, error, lastUpdated }) {
  const currencies = data?.currencies ?? [];

  return (
    <Card title="Wallet Balance" lastUpdated={lastUpdated}>
      {error ? (
        <p className="text-xs text-text-muted italic">{error}</p>
      ) : loading && !data ? (
        <div className="text-xs text-text-muted italic p-2">Loading…</div>
      ) : currencies.length === 0 ? (
        <div className="text-xs text-text-muted italic">No balance data</div>
      ) : (
        <dl className="space-y-0">
          {currencies.map((c) => (
            <KV
              key={c.currency}
              label={c.currency}
              value={
                c.free != null
                  ? `${c.free.toFixed(4)} free / ${(c.total ?? c.free).toFixed(4)} total`
                  : "—"
              }
            />
          ))}
          {data.note && (
            <p className="text-xxs text-text-muted italic pt-2">{data.note}</p>
          )}
        </dl>
      )}
    </Card>
  );
}

// ─── Live config ─────────────────────────────────────────────────────────────

function ConfigPanel({ data, loading, error, lastUpdated }) {
  if (loading && !data) {
    return (
      <Card title="Live Config">
        <div className="text-xs text-text-muted italic p-2">Loading…</div>
      </Card>
    );
  }
  if (error || !data) {
    return (
      <Card title="Live Config">
        <div className="text-xs text-text-muted italic p-2">{error ?? "No config"}</div>
      </Card>
    );
  }

  const cfg = data;
  const ft = cfg.freqai ?? cfg.freqAI ?? {};
  const ep = cfg.exchange ?? {};
  const env = cfg.env_vars ?? {};
  const identifier = ft.identifier ?? env.FREQTRADE__FREQAI__IDENTIFIER ?? "—";

  const thresholds = [
    ["Long threshold", env.FREQAI_LONG_THRESHOLD ?? cfg.long_threshold],
    ["Short threshold", env.FREQAI_SHORT_THRESHOLD ?? cfg.short_threshold],
    ["K_TP (profit mult)", env.FREQAI_K_TP ?? cfg.k_tp],
    ["K_SL (stop mult)", env.FREQAI_K_SL ?? cfg.k_sl],
    ["Stability N", env.FREQAI_STABILITY_N ?? cfg.stability_n],
    ["Daily loss limit", env.FREQAI_DAILY_LOSS_LIMIT ?? cfg.daily_loss_limit],
    ["Feature set", env.FREQAI_FEATURE_SET ?? "all"],
  ];

  return (
    <div className="space-y-4">
      <Section title="Strategy">
        <KV label="Strategy" value={displayStrategyName(cfg.strategy)} />
        <KV label="FreqAI Identifier" value={identifier} />
        <KV label="Timeframe" value={cfg.timeframe} />
        <KV label="Max open trades" value={cfg.max_open_trades} />
        {/* timeframe is now switchable via the Timeframe card above */}
        <KV label="Stake amount" value={cfg.stake_amount != null ? `${cfg.stake_amount} USDT` : "unlimited"} />
        <KV label="Dry run" value={cfg.dry_run ? "Yes" : "No"} tone={cfg.dry_run ? "warn" : "profit"} />
      </Section>

      <Section title="Live Thresholds (env vars)">
        {thresholds.map(([label, val]) => (
          <KV key={label} label={label} value={val ?? "default"} />
        ))}
      </Section>

      <Section title="Exchange">
        <KV label="Exchange" value={ep.name} />
        <KV label="Futures mode" value={ep.futures_mode != null ? String(ep.futures_mode) : (ep.margin_mode ? ep.margin_mode : "isolated")} />
        <KV label="Live retrain hours" value={ft.live_retrain_hours ?? "—"} />
        <KV label="Startup candles" value={ft.startup_candle_count ?? cfg.startup_candle_count ?? "—"} />
      </Section>
    </div>
  );
}

// ─── Tab root ────────────────────────────────────────────────────────────────

export default function Settings() {
  const config = usePolling(getStrategyConfig, 300000); // 5 min — config rarely changes
  const whitelist = usePolling(getWhitelist, 60000);
  const balance = usePolling(getBalance, 60000);

  return (
    <div className="space-y-4">
      <TimeframeCard />
      <ParamControls />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-4">
          <ConfigPanel
            data={config.data}
            loading={config.loading}
            error={config.error}
            lastUpdated={config.lastUpdated}
          />
        </div>
        <div className="space-y-4">
          <WhitelistPanel
            data={whitelist.data}
            loading={whitelist.loading}
            error={whitelist.error}
            lastUpdated={whitelist.lastUpdated}
          />
          <BalancePanel
            data={balance.data}
            loading={balance.loading}
            error={balance.error}
            lastUpdated={balance.lastUpdated}
          />
        </div>
      </div>
    </div>
  );
}
