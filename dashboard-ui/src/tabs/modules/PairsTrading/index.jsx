import { useMemo } from "react";

import ModuleShell from "../../../components/ModuleShell";
import Card from "../../../components/Card";
import Table from "../../../components/Table";
import Badge from "../../../components/Badge";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getPairsScan, getPairsPortfolio } from "../../../api/client";

/**
 * Pairs Trading module — market-neutral statistical arbitrage, now PAPER-trading.
 * A scanner finds correlated coins whose spread has stretched; the paper executor
 * opens simulated long/short positions and books P&L when the spread reverts.
 */

// ─── Active paper positions ───────────────────────────────────────────────────
function PositionsCard({ data, lastUpdated }) {
  const rows = useMemo(
    () => (data?.positions || []).map((p, i) => ({ ...p, id: i })),
    [data]
  );
  const cols = [
    {
      key: "trade",
      label: "Position",
      render: (r) => (
        <Badge variant={r.side === 1 ? "long" : "short"} size="xs">{r.trade}</Badge>
      ),
    },
    {
      key: "entry_z",
      label: <InfoTip label="Entry" text="How stretched the spread was when we opened (in standard deviations)." />,
      align: "right",
      mono: true,
      render: (r) => (r.entry_z != null ? `${r.entry_z > 0 ? "+" : ""}${r.entry_z.toFixed(2)}σ` : "—"),
    },
    {
      key: "notional",
      label: "Size",
      align: "right",
      mono: true,
      render: (r) => (r.notional != null ? `${r.notional.toFixed(0)}` : "—"),
    },
    {
      key: "unrealized",
      label: <InfoTip label="P&L" text="Live profit/loss if we closed this pair right now (after entry fees)." />,
      align: "right",
      mono: true,
      render: (r) => {
        if (r.unrealized == null) return "—";
        const cls = r.unrealized >= 0 ? "text-profit" : "text-loss";
        return <span className={cls}>{r.unrealized >= 0 ? "+" : ""}{r.unrealized.toFixed(2)}</span>;
      },
    },
  ];
  return (
    <Card
      title="Active Positions"
      subtitle={data?.open_count ? `${data.open_count} paper position${data.open_count > 1 ? "s" : ""}` : "none open"}
      lastUpdated={lastUpdated}
    >
      <Table
        columns={cols}
        rows={rows}
        emptyMessage="No open positions — waiting for a spread to stretch past ±2σ."
      />
    </Card>
  );
}

// ─── Scanner / opportunities ──────────────────────────────────────────────────
function OpportunitiesCard({ data, loading, lastUpdated }) {
  const rows = useMemo(
    () => (data?.pairs || []).slice(0, 12).map((r, i) => ({ ...r, id: i })),
    [data]
  );
  const cols = [
    {
      key: "pair",
      label: "Pair",
      mono: true,
      render: (r) => (
        <span className="font-mono">{r.a}<span className="text-text-muted"> / </span>{r.b}</span>
      ),
    },
    {
      key: "corr",
      label: <InfoTip label="Correlation" text="How tightly the two coins move together (1.0 = identical). Higher = more reliable pair." />,
      align: "right",
      mono: true,
      render: (r) => (r.corr != null ? r.corr.toFixed(2) : "—"),
    },
    {
      key: "z",
      label: <InfoTip label="Stretch" text="How far the spread has drifted from normal, in standard deviations. Beyond ±2 is the entry zone." />,
      align: "right",
      mono: true,
      render: (r) => {
        if (r.z == null) return "—";
        const hot = Math.abs(r.z) >= 2;
        return <span className={hot ? "text-warn font-semibold" : "text-text-muted"}>{r.z > 0 ? "+" : ""}{r.z.toFixed(2)}σ</span>;
      },
    },
    {
      key: "half_life_h",
      label: <InfoTip label="Revert in" text="Estimated time for the spread to close halfway back to normal. Shorter = faster, more tradeable." />,
      align: "right",
      mono: true,
      render: (r) => (r.half_life_h != null ? `${r.half_life_h.toFixed(0)}h` : "—"),
    },
    {
      key: "signal",
      label: "Would trade",
      render: (r) =>
        r.signal === "in range"
          ? <span className="text-xxs text-text-muted">in range</span>
          : <Badge variant="info" size="xs">{r.signal}</Badge>,
    },
  ];
  return (
    <Card
      title="Scanner — opportunities"
      subtitle={`${data?.scanned ?? "—"} coins · ${data?.candidates ?? 0} correlated pairs · sorted by stretch`}
      lastUpdated={lastUpdated}
    >
      <Table columns={cols} rows={rows} loading={loading && !data} emptyMessage="No correlated pairs found." />
    </Card>
  );
}

export default function PairsTradingModule() {
  const scan = usePolling(getPairsScan, 300000);
  const port = usePolling(getPairsPortfolio, 30000);

  const realized = port.data?.realized_pnl ?? 0;
  const unreal = port.data?.unrealized_pnl ?? 0;
  const total = realized + unreal;

  const hero = {
    label: "Paper P&L",
    value: port.data ? `${total >= 0 ? "+" : ""}${total.toFixed(2)}` : "—",
    unit: port.data ? "USDT" : "",
    tone: total > 0 ? "profit" : total < 0 ? "loss" : "default",
  };

  return (
    <ModuleShell
      name="Pairs Trading"
      status="paper"
      tagline="Bets that two related coins drift back together — profits whether the market goes up or down."
      howItMakesMoney="When the price spread between two correlated coins stretches past ±2σ, it buys the cheap one and shorts the rich one; it books profit when the spread reverts to normal. Market-neutral, paper-traded."
      hero={hero}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PositionsCard data={port.data} lastUpdated={port.lastUpdated} />
        <OpportunitiesCard data={scan.data} loading={scan.loading} lastUpdated={scan.lastUpdated} />
      </div>

      <Card title="How it's doing" className="mt-4">
        <p className="text-xs text-text-secondary leading-relaxed">
          Realized {realized >= 0 ? "+" : ""}{realized.toFixed(2)} USDT · open {unreal >= 0 ? "+" : ""}{unreal.toFixed(2)} USDT
          across {port.data?.open_count ?? 0} paper position{(port.data?.open_count ?? 0) === 1 ? "" : "s"}.
          The scanner runs hourly: it opens a market-neutral long/short when a correlated pair stretches
          past ±2σ and closes it when the spread reverts (or stops out if it keeps diverging). Paper only —
          no real orders, and slippage/borrow costs aren't modeled yet.
        </p>
      </Card>
    </ModuleShell>
  );
}
