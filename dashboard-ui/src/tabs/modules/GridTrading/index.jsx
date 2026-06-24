import ModuleShell from "../../../components/ModuleShell";
import ComingSoon from "../../../components/ComingSoon";

/**
 * Grid Trading module — range-bound oscillation harvesting. Placeholder for now;
 * the live volatility-scanner preview lands in Phase 2.
 */
export default function GridTradingModule() {
  return (
    <ModuleShell
      name="Grid Trading"
      status="soon"
      tagline="Profits from a coin bouncing inside a price range — no direction guess needed."
      howItMakesMoney="Places a ladder of buy and sell orders across a range; every time price oscillates up and down it buys low and sells high, banking the difference on each swing."
      hero={{ label: "Status", value: "Roadmap" }}
    >
      <ComingSoon
        bullets={[
          "Detects coins trading sideways inside a stable range (where directional bets bleed).",
          "Lays a grid of buy and sell orders across that range.",
          "Each up-and-down swing books a small profit — the choppier the range, the more it earns.",
          "Complements directional trading: it makes money in exactly the flat markets that hurt the ML strategy.",
        ]}
      />
    </ModuleShell>
  );
}
