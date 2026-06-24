import ModuleShell from "../../../components/ModuleShell";
import ComingSoon from "../../../components/ComingSoon";

/**
 * Pairs Trading module — market-neutral statistical arbitrage. Placeholder for
 * now; the live cointegration-scanner preview lands in Phase 2.
 */
export default function PairsTradingModule() {
  return (
    <ModuleShell
      name="Pairs Trading"
      status="soon"
      tagline="Bets that two related coins drift back together — profits whether the market goes up or down."
      howItMakesMoney="When the price ratio between two correlated coins stretches unusually wide, buy the cheap one and short the rich one; the income comes when the ratio snaps back to normal."
      hero={{ label: "Status", value: "Roadmap" }}
    >
      <ComingSoon
        bullets={[
          "Continuously scans every coin pair to find ones that historically move together (cointegration).",
          "When their price ratio drifts far from its normal range, opens a market-neutral long/short trade.",
          "Earns when the ratio reverts — no dependence on the overall market direction.",
          "This is where the ML brain has a genuine edge: spreads are mathematically mean-reverting, unlike raw price.",
        ]}
      />
    </ModuleShell>
  );
}
