import { useMemo } from "react";

import ModuleShell from "../../../components/ModuleShell";
import ComingSoon from "../../../components/ComingSoon";
import Table from "../../../components/Table";
import Badge from "../../../components/Badge";
import InfoTip from "../../../components/InfoTip";
import { usePolling } from "../../../api/hooks";
import { getPairsScan } from "../../../api/client";

/**
 * Pairs Trading module — market-neutral statistical arbitrage. Not live yet, but
 * the cointegration-lite scanner below runs on real current data to preview what
 * the module will hunt for: correlated coins whose spread has stretched and is
 * likely to revert.
 */
function ScannerPreview() {
  const { data, loading, lastUpdated } = usePolling(getPairsScan, 300000);

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
        <span className="font-mono">
          {r.a}<span className="text-text-muted"> / </span>{r.b}
        </span>
      ),
    },
    {
      key: "corr",
      label: <InfoTip label="Correlation" text="How tightly the two coins move together (1.0 = identical). Higher means a more reliable pair." />,
      align: "right",
      mono: true,
      render: (r) => (r.corr != null ? r.corr.toFixed(2) : "—"),
    },
    {
      key: "z",
      label: <InfoTip label="Stretch" text="How far the spread has drifted from normal, in standard deviations. Beyond ±2 is the classic entry zone." />,
      align: "right",
      mono: true,
      render: (r) => {
        const z = r.z;
        if (z == null) return "—";
        const hot = Math.abs(z) >= 2;
        return <span className={hot ? "text-warn font-semibold" : "text-text-muted"}>{z > 0 ? "+" : ""}{z.toFixed(2)}σ</span>;
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
        r.signal === "in range" ? (
          <span className="text-xxs text-text-muted">in range</span>
        ) : (
          <Badge variant="info" size="xs">{r.signal}</Badge>
        ),
    },
  ];

  return (
    <div>
      <p className="text-xxs text-text-tertiary mb-2">
        Live scan of {data?.scanned ?? "—"} coins over the last 30 days · {data?.candidates ?? 0} correlated
        pairs found · sorted by how stretched each spread is right now.
      </p>
      <Table
        columns={cols}
        rows={rows}
        loading={loading && !data}
        emptyMessage="No correlated pairs found in the current data."
      />
    </div>
  );
}

export default function PairsTradingModule() {
  return (
    <ModuleShell
      name="Pairs Trading"
      status="soon"
      tagline="Bets that two related coins drift back together — profits whether the market goes up or down."
      howItMakesMoney="When the price ratio between two correlated coins stretches unusually wide, buy the cheap one and short the rich one; the income comes when the ratio snaps back to normal."
      hero={{ label: "Status", value: "Preview" }}
    >
      <ComingSoon
        intro={
          "The scanner below is LIVE — it's analysing real markets right now. " +
          "What's not built yet is the executor that automatically places and manages these trades. " +
          "That's what “Soon” means. Here's the full picture:"
        }
        bullets={[
          "Continuously scans every coin pair to find ones that historically move together (correlation / cointegration). ✓ live below",
          "When their price spread drifts far from its normal range, opens a market-neutral long/short trade. ⏳ executor not built yet",
          "Earns when the spread reverts — no dependence on the overall market direction.",
          "This is where the ML brain has a genuine edge: spreads are mathematically mean-reverting, unlike raw price.",
        ]}
        previewTitle="Live scanner — what it's watching right now"
        preview={<ScannerPreview />}
      />
    </ModuleShell>
  );
}
