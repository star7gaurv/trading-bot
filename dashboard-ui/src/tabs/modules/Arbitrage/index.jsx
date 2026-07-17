import ModuleShell from "../../../components/ModuleShell";
import Card from "../../../components/Card";
import Table from "../../../components/Table";
import Badge from "../../../components/Badge";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getArbitrage } from "../../../api/client";
import { formatRelative } from "../../../utils/format";

/**
 * Arbitrage module — watches many exchanges at once for price gaps on the same
 * coin. Only gaps that are actually plausible to capture (same-exchange or
 * pre-funded-capital cross-exchange) ever count as paper profit; gaps found on
 * a thinner, less-connected exchange are logged as "observed" only, since the
 * time to move money there almost always outlasts the gap. Paper-traded today.
 */

const TYPE_LABEL = {
  intra_exchange_basis: "Same-exchange",
  cross_exchange_prefunded: "Cross-exchange",
  cross_exchange_transfer: "Cross-exchange (far)",
};

function EventsTable({ events }) {
  const rows = (events || []).map((e, i) => ({ ...e, id: i }));
  const cols = [
    {
      key: "type",
      label: "Result",
      render: (r) =>
        r.type === "capture" ? (
          <Badge variant="ok" size="xs">Captured</Badge>
        ) : (
          <Badge variant="unknown" size="xs">Observed only</Badge>
        ),
    },
    {
      key: "symbol",
      label: "Coin",
      mono: true,
    },
    {
      key: "opportunity_type",
      label: <InfoTip label="Kind" text="Same-exchange = spot vs. futures gap on one venue. Cross-exchange = the same coin priced differently on two venues." />,
      render: (r) => TYPE_LABEL[r.opportunity_type] || r.opportunity_type,
    },
    {
      key: "route",
      label: "Route",
      mono: true,
      render: (r) => `${r.buy_exchange} → ${r.sell_exchange}`,
    },
    {
      key: "gap",
      label: <InfoTip label="Gap" text="Price difference between the two legs, before fees." />,
      align: "right",
      mono: true,
      render: (r) => {
        const pct = r.gross_gap_pct ?? r.gap_pct ?? 0;
        return <span className="text-text-secondary">{pct.toFixed(3)}%</span>;
      },
    },
    {
      key: "net_pnl",
      label: "Net P&L",
      align: "right",
      mono: true,
      render: (r) => {
        if (r.type !== "capture") return <span className="text-text-muted">—</span>;
        const v = r.net_pnl ?? 0;
        return <span className={v >= 0 ? "text-profit" : "text-loss"}>{v >= 0 ? "+" : ""}{v.toFixed(3)}</span>;
      },
    },
    {
      key: "ts",
      label: "When",
      align: "right",
      mono: true,
      render: (r) => (r.ts ? formatRelative(new Date(r.ts).getTime()) : "—"),
    },
  ];
  return (
    <Table
      columns={cols}
      rows={rows}
      emptyMessage="No gaps seen yet — the feed watches quietly until one clears its fees."
      maxHeight="360px"
    />
  );
}

function FeedHealthBadge({ alive, ageS, exchangeCount }) {
  if (alive == null) return null;
  return (
    <span className="flex items-center gap-1.5 text-xxs">
      <span className={`w-1.5 h-1.5 rounded-full inline-block ${alive ? "bg-profit animate-pulse" : "bg-loss"}`} />
      {alive ? (
        <span className="text-text-tertiary">{exchangeCount} exchanges live · updated {ageS}s ago</span>
      ) : ageS == null ? (
        <span className="text-loss">Feed never started</span>
      ) : (
        <span className="text-loss">Feed not reporting (last update {ageS}s ago)</span>
      )}
    </span>
  );
}

export default function ArbitrageModule() {
  const { data, lastUpdated } = usePolling(getArbitrage, 15000);

  const realized = data?.realized_pnl ?? 0;
  const capturesTotal = data?.captures_total ?? 0;
  const observationsTotal = data?.observations_total ?? 0;

  const hero = {
    label: "Paper P&L",
    value: data ? `${realized >= 0 ? "+" : ""}${realized.toFixed(2)}` : "—",
    unit: data ? "USDT" : "",
    tone: realized > 0 ? "profit" : realized < 0 ? "loss" : "default",
  };

  return (
    <ModuleShell
      name="Arbitrage"
      status="paper"
      tagline="Watches many exchanges at once for the same coin priced differently — profits from the gap, not from guessing direction."
      howItMakesMoney="Buys where a coin is cheaper and sells where it's pricier, at the same time. Only counts it as profit when both sides are realistically reachable together (same exchange, or exchanges we treat as pre-funded); gaps that need a slow transfer between venues are logged as sightings only, never as money made."
      hero={hero}
      actions={
        <FeedHealthBadge
          alive={data?.feed_alive}
          ageS={data?.feed_age_s}
          exchangeCount={data?.exchanges_reporting}
        />
      }
    >
      <Card
        title="Recent activity"
        subtitle={`${capturesTotal} captured · ${observationsTotal} observed-only (lifetime)`}
        lastUpdated={lastUpdated}
      >
        <EventsTable events={data?.recent_events} />
      </Card>

      <Card title="How this is honest about what's real" className="mt-4">
        <p className="text-xs text-text-secondary leading-relaxed">
          Real arbitrage isn't one thing. A price gap between a coin's spot and futures price on
          the <strong className="text-text-primary">same exchange</strong> can genuinely be
          captured instantly. A gap between{" "}
          <strong className="text-text-primary">two well-connected exchanges</strong> is also
          counted, on the assumption capital already sits on both sides. But a gap that only
          shows up because we're watching a smaller, less-connected exchange usually can't be
          captured for real — moving money there takes longer than the gap tends to last. Those
          get logged as <strong className="text-text-primary">sightings</strong> so watching many
          exchanges still does its job (finding where gaps exist), without pretending every
          sighting is money in the bank.
        </p>
      </Card>
    </ModuleShell>
  );
}
