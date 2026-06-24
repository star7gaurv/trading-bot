import ModuleShell from "../../../components/ModuleShell";
import Card from "../../../components/Card";
import Table from "../../../components/Table";
import Badge from "../../../components/Badge";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getFundingFarm } from "../../../api/client";

/**
 * Funding Farm module — market-neutral cash-and-carry. Holds a coin on the spot
 * market and shorts its perpetual by the same size, collecting the funding fee
 * with no bet on price direction. Paper-traded today.
 */

function OpportunitiesTable({ symbols, threshold }) {
  const rows = (symbols || []).map((s, i) => ({ ...s, id: i }));
  const cols = [
    {
      key: "symbol",
      label: "Coin",
      mono: true,
      render: (r) => (r.symbol || "").replace("USDT", ""),
    },
    {
      key: "apr",
      label: <InfoTip label="APR" text="Annualized funding income if the current rate held for a year." />,
      align: "right",
      mono: true,
      render: (r) => {
        const pct = (r.apr ?? 0) * 100;
        const cls = Math.abs(r.apr ?? 0) >= threshold ? "text-profit" : "text-text-muted";
        return <span className={cls}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</span>;
      },
    },
    {
      key: "gap",
      label: <InfoTip label="Gap" text="How far below the entry threshold this coin is. 0 means it qualifies." />,
      align: "right",
      mono: true,
      render: (r) => {
        const g = (r.gap_to_threshold ?? 0) * 100;
        return g <= 0 ? "—" : `${g.toFixed(1)}%`;
      },
    },
    {
      key: "status",
      label: "Status",
      align: "right",
      render: (r) =>
        r.at_threshold ? (
          <Badge variant="ok" size="xs">Qualifies</Badge>
        ) : (
          <Badge variant="unknown" size="xs">Below target</Badge>
        ),
    },
  ];
  return (
    <Table
      columns={cols}
      rows={rows}
      emptyMessage="No funding data yet."
      maxHeight="340px"
    />
  );
}

function PositionsTable({ positions }) {
  const rows = Object.entries(positions || {}).map(([symbol, p], i) => ({
    id: i,
    symbol,
    ...p,
  }));
  const cols = [
    { key: "symbol", label: "Coin", mono: true, render: (r) => r.symbol.replace("USDT", "") },
    {
      key: "notional",
      label: <InfoTip label="Size" text="Position size in USDT (held long on spot, short on the perpetual)." />,
      align: "right",
      mono: true,
      render: (r) => (r.notional != null ? r.notional.toFixed(0) : "—"),
    },
    {
      key: "funding_collected",
      label: <InfoTip label="Earned" text="Funding fees collected so far on this position." />,
      align: "right",
      mono: true,
      render: (r) => {
        const v = r.funding_collected ?? 0;
        return <span className={v >= 0 ? "text-profit" : "text-loss"}>{v >= 0 ? "+" : ""}{v.toFixed(3)}</span>;
      },
    },
    {
      key: "fees_paid",
      label: "Fees",
      align: "right",
      mono: true,
      render: (r) => (r.fees_paid != null ? `-${r.fees_paid.toFixed(3)}` : "—"),
    },
    {
      key: "entry_apr",
      label: "Entry APR",
      align: "right",
      mono: true,
      render: (r) => (r.entry_apr != null ? `${(r.entry_apr * 100).toFixed(1)}%` : "—"),
    },
  ];
  return (
    <Table
      columns={cols}
      rows={rows}
      emptyMessage="No open positions — the farm only opens when a coin's funding clears the target."
    />
  );
}

export default function FundingFarmModule() {
  const { data, lastUpdated } = usePolling(getFundingFarm, 60000);

  const realized = data?.realized_pnl ?? 0;
  const threshold = data?.threshold ?? 0.15;
  const posCount = Object.keys(data?.positions || {}).length;

  const hero = {
    label: "Paper P&L",
    value: data ? `${realized >= 0 ? "+" : ""}${realized.toFixed(2)}` : "—",
    unit: data ? "USDT" : "",
    tone: realized > 0 ? "profit" : realized < 0 ? "loss" : "default",
  };

  return (
    <ModuleShell
      name="Funding Farm"
      status="paper"
      tagline="Collects funding fees with no bet on price direction — fully market-neutral."
      howItMakesMoney="Holds a coin on spot and shorts its perpetual by the same amount; the funding fee paid between traders is the income, while the price exposure cancels out."
      hero={hero}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card
          title="Opportunities"
          subtitle={`Current funding APR vs the ${(threshold * 100).toFixed(0)}% entry target`}
          lastUpdated={lastUpdated}
        >
          <OpportunitiesTable symbols={data?.symbols} threshold={threshold} />
        </Card>

        <Card
          title="Active Positions"
          subtitle={posCount > 0 ? `${posCount} paper position${posCount > 1 ? "s" : ""}` : "none open"}
          lastUpdated={lastUpdated}
        >
          <PositionsTable positions={data?.positions} />
        </Card>
      </div>

      <Card title="How the farm is doing" className="mt-4">
        <p className="text-xs text-text-secondary leading-relaxed">
          {posCount === 0 ? (
            <>
              The farm is <strong className="text-text-primary">dormant</strong> right now — no coin's
              funding rate clears the {(threshold * 100).toFixed(0)}% annualized target, so opening a
              position wouldn't out-earn the trading fees. This is the correct, safe behaviour in a
              calm/bear market. It will wake up automatically when funding spikes.
            </>
          ) : (
            <>
              {posCount} paper position{posCount > 1 ? "s" : ""} open, collecting funding fees with no
              directional risk. Paper P&L so far: {realized >= 0 ? "+" : ""}{realized.toFixed(2)} USDT.
            </>
          )}
        </p>
      </Card>
    </ModuleShell>
  );
}
