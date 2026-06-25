import { useMemo } from "react";

import ModuleShell from "../../../components/ModuleShell";
import ComingSoon from "../../../components/ComingSoon";
import Table from "../../../components/Table";
import Badge from "../../../components/Badge";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getGridScan } from "../../../api/client";

/**
 * Grid Trading module — range-bound oscillation harvesting. Not live yet, but the
 * scanner below ranks coins by how grid-friendly they are right now (ranging but
 * still moving), previewing what the module will target.
 */
function ScannerPreview() {
  const { data, loading, lastUpdated } = usePolling(getGridScan, 300000);

  const rows = useMemo(
    () => (data?.coins || []).slice(0, 12).map((r, i) => ({ ...r, id: i })),
    [data]
  );

  const cols = [
    { key: "symbol", label: "Coin", mono: true },
    {
      key: "efficiency_ratio",
      label: <InfoTip label="Trendiness" text="0 = pure chop (ideal for a grid), 1 = strong trend (price walks out of the grid). Lower is better here." />,
      align: "right",
      mono: true,
      render: (r) => (r.efficiency_ratio != null ? r.efficiency_ratio.toFixed(2) : "—"),
    },
    {
      key: "volatility_pct",
      label: <InfoTip label="Swing" text="Average hourly price movement — the oscillation a grid converts into profit. Needs to be high enough to beat fees." />,
      align: "right",
      mono: true,
      render: (r) => (r.volatility_pct != null ? `${r.volatility_pct.toFixed(2)}%` : "—"),
    },
    {
      key: "range_pct",
      label: <InfoTip label="Range" text="How wide the price band has been — roughly how wide to set the grid." />,
      align: "right",
      mono: true,
      render: (r) => (r.range_pct != null ? `${r.range_pct.toFixed(0)}%` : "—"),
    },
    {
      key: "verdict",
      label: "Verdict",
      render: (r) => {
        const v = r.verdict || "";
        const variant = v.startsWith("ranging") ? "ok" : v.startsWith("trending") ? "loss" : "unknown";
        return <Badge variant={variant} size="xs">{v}</Badge>;
      },
    },
  ];

  return (
    <div>
      <p className="text-xxs text-text-tertiary mb-2">
        Live scan of {data?.scanned ?? "—"} coins over the last 14 days · ranked by how
        grid-friendly each is right now (ranging, but still swinging).
      </p>
      <Table
        columns={cols}
        rows={rows}
        loading={loading && !data}
        emptyMessage="No price data to scan."
      />
    </div>
  );
}

export default function GridTradingModule() {
  return (
    <ModuleShell
      name="Grid Trading"
      status="soon"
      tagline="Profits from a coin bouncing inside a price range — no direction guess needed."
      howItMakesMoney="Places a ladder of buy and sell orders across a range; every time price oscillates up and down it buys low and sells high, banking the difference on each swing."
      hero={{ label: "Status", value: "Preview" }}
    >
      <ComingSoon
        intro={
          "The scanner below is LIVE — it's ranking real coins by grid-friendliness right now. " +
          "What's not built yet is the executor that lays the grid and places the orders. " +
          "That's what “Soon” means. Here's the full picture:"
        }
        bullets={[
          "Detects coins trading sideways inside a stable range (where directional bets bleed). ✓ live below",
          "Lays a grid of buy and sell orders across that range. ⏳ executor not built yet",
          "Each up-and-down swing books a small profit — the choppier the range, the more it earns.",
          "Complements directional trading: it makes money in exactly the flat markets that hurt the ML strategy.",
        ]}
        previewTitle="Live scanner — best grid candidates right now"
        preview={<ScannerPreview />}
      />
    </ModuleShell>
  );
}
