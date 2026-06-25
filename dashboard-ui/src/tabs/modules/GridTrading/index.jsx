import { useMemo } from "react";

import ModuleShell from "../../../components/ModuleShell";
import Card from "../../../components/Card";
import Table from "../../../components/Table";
import Badge from "../../../components/Badge";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getGridScan, getGridPortfolio } from "../../../api/client";

/**
 * Grid Trading module — range-bound oscillation harvesting, paper-traded.
 *
 * The scanner picks coins that are choppy (low Kaufman ER) but still moving
 * (enough hourly swing to beat fees).  The paper executor lays a virtual 10-level
 * grid and counts every time price crosses a grid line, booking the cell width
 * minus fee as profit.  No real orders are placed.
 */

// ─── Active paper grids ───────────────────────────────────────────────────────
function ActiveGridsCard({ data, lastUpdated }) {
  const rows = useMemo(
    () => (data?.grids || []).map((g, i) => ({ ...g, id: i })),
    [data]
  );

  const cols = [
    {
      key: "symbol",
      label: "Coin",
      mono: true,
    },
    {
      key: "range",
      label: <InfoTip label="Grid range" text="Price band the grid covers. Each of the 10 levels is spaced evenly across this band — every time price bounces through one it earns the cell width." />,
      mono: true,
      render: (r) =>
        r.low != null && r.high != null
          ? <span className="text-xxs">{r.low.toPrecision(4)} – {r.high.toPrecision(4)}</span>
          : "—",
    },
    {
      key: "spacing_pct",
      label: <InfoTip label="Cell %" text="Width of each grid cell as a % of entry price. Profit per bounce = cell% × notional per level − fee." />,
      align: "right",
      mono: true,
      render: (r) => (r.spacing_pct != null ? `${r.spacing_pct.toFixed(2)}%` : "—"),
    },
    {
      key: "in_range",
      label: "In range",
      render: (r) =>
        r.in_range == null
          ? "—"
          : r.in_range
          ? <Badge variant="ok" size="xs">yes</Badge>
          : <Badge variant="loss" size="xs">broke out</Badge>,
    },
    {
      key: "total_crossings",
      label: <InfoTip label="Fills" text="How many times price has crossed a grid level since deployment. Each fill earns one cell width." />,
      align: "right",
      mono: true,
    },
    {
      key: "net_pnl",
      label: "Net P&L",
      align: "right",
      mono: true,
      render: (r) => {
        if (r.net_pnl == null) return "—";
        const cls = r.net_pnl >= 0 ? "text-profit" : "text-loss";
        return (
          <span className={cls}>
            {r.net_pnl >= 0 ? "+" : ""}
            {r.net_pnl.toFixed(3)}
          </span>
        );
      },
    },
  ];

  return (
    <Card
      title="Active paper grids"
      subtitle={
        data?.open_count
          ? `${data.open_count} grid${data.open_count !== 1 ? "s" : ""} deployed · scanner checks hourly`
          : "no grids open — scanner will deploy when a qualifying coin is detected"
      }
      lastUpdated={lastUpdated}
    >
      <Table
        columns={cols}
        rows={rows}
        emptyMessage="Waiting for a ranging coin to appear in the scanner. The hourly cron will deploy automatically."
      />
    </Card>
  );
}

// ─── Grid-suitability scanner ─────────────────────────────────────────────────
function ScannerCard({ data, loading, lastUpdated }) {
  const rows = useMemo(
    () => (data?.coins || []).slice(0, 12).map((r, i) => ({ ...r, id: i })),
    [data]
  );

  const cols = [
    { key: "symbol", label: "Coin", mono: true },
    {
      key: "efficiency_ratio",
      label: <InfoTip label="Trendiness" text="0 = pure chop (ideal for a grid), 1 = strong trend (price walks out). Lower is better." />,
      align: "right",
      mono: true,
      render: (r) =>
        r.efficiency_ratio != null ? r.efficiency_ratio.toFixed(2) : "—",
    },
    {
      key: "volatility_pct",
      label: <InfoTip label="Swing/h" text="Average hourly price movement — the oscillation a grid converts into profit. Must beat fees." />,
      align: "right",
      mono: true,
      render: (r) =>
        r.volatility_pct != null ? `${r.volatility_pct.toFixed(2)}%` : "—",
    },
    {
      key: "range_pct",
      label: <InfoTip label="Band" text="14-day price range as % of mid. Sets how wide the grid is placed." />,
      align: "right",
      mono: true,
      render: (r) =>
        r.range_pct != null ? `${r.range_pct.toFixed(0)}%` : "—",
    },
    {
      key: "verdict",
      label: "Verdict",
      render: (r) => {
        const v = r.verdict || "";
        const variant = v.startsWith("ranging")
          ? "ok"
          : v.startsWith("trending")
          ? "loss"
          : "unknown";
        return <Badge variant={variant} size="xs">{v}</Badge>;
      },
    },
  ];

  return (
    <Card
      title="Live scanner — best grid candidates"
      subtitle={`${data?.scanned ?? "—"} coins · ranked by grid score (swing × choppiness) · 14-day window`}
      lastUpdated={lastUpdated}
    >
      <p className="text-xxs text-text-tertiary mb-2">
        The scanner feeds the executor: "ranging — good" coins at the top are the
        ones the hourly cron targets for grid deployment.
      </p>
      <Table
        columns={cols}
        rows={rows}
        loading={loading && !data}
        emptyMessage="No price data to scan."
      />
    </Card>
  );
}

// ─── Module root ─────────────────────────────────────────────────────────────
export default function GridTradingModule() {
  const port = usePolling(getGridPortfolio, 30000);
  const scan = usePolling(getGridScan, 300000);

  const realized = port.data?.realized_pnl ?? 0;
  const openPnl  = port.data?.open_pnl ?? 0;
  const total    = realized + openPnl;

  const hero = {
    label: "Paper P&L",
    value: port.data ? `${total >= 0 ? "+" : ""}${total.toFixed(2)}` : "—",
    unit: port.data ? "USDT" : "",
    tone: total > 0 ? "profit" : total < 0 ? "loss" : "default",
  };

  return (
    <ModuleShell
      name="Grid Trading"
      status="paper"
      tagline="Profits from a coin bouncing inside a price range — no direction guess needed."
      howItMakesMoney="Places a ladder of virtual buy and sell orders across a detected range. Every time price oscillates up and down it earns the gap between two rungs minus fees. Paper-traded so far — building a track record before any real execution."
      hero={hero}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ActiveGridsCard data={port.data} lastUpdated={port.lastUpdated} />
        <ScannerCard data={scan.data} loading={scan.loading} lastUpdated={scan.lastUpdated} />
      </div>

      <Card title="How it's doing" className="mt-4">
        <p className="text-xs text-text-secondary leading-relaxed">
          Realized {realized >= 0 ? "+" : ""}{realized.toFixed(2)} USDT from closed grids ·
          open grids: {openPnl >= 0 ? "+" : ""}{openPnl.toFixed(2)} USDT ·
          {port.data?.open_count ?? 0} grid{(port.data?.open_count ?? 0) !== 1 ? "s" : ""} deployed
          (max 3, 300 USDT each, 10 levels).{" "}
          The cron runs hourly at :40 UTC — it ticks open grids, closes any that broke out of range,
          and opens new ones on the best ranging coins. Paper only: no real orders, slippage not
          modeled.
        </p>
      </Card>
    </ModuleShell>
  );
}
