import { useState } from "react";

import ModuleShell from "../../../components/ModuleShell";
import SubTabs from "../../../components/SubTabs";
import { usePolling } from "../../../api/hooks";
import { getProfitSummary } from "../../../api/client";

import Overview from "../../Overview";
import Trades from "../../Trades";
import Signals from "../../Signals";
import Performance from "../../Performance";

/**
 * Directional Trading module — the Live ML strategy that predicts price
 * direction and trades long or short. Wraps the existing Overview / Trades /
 * Signals / Performance views as sub-tabs inside the self-explanatory shell.
 */
const SUB_TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "trades", label: "Trades" },
  { id: "performance", label: "Performance" },
  { id: "signals", label: "Signals" },
];

export default function DirectionalModule({ onNavigateTab }) {
  const [sub, setSub] = useState("dashboard");
  const profit = usePolling(getProfitSummary, 30000);

  const pnl = profit.data?.profit_closed_coin;
  const hero = {
    label: "Total P&L (dry-run)",
    value: pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}` : "—",
    unit: pnl != null ? "USDT" : "",
    tone: pnl == null ? "default" : pnl >= 0 ? "profit" : "loss",
  };

  return (
    <ModuleShell
      name="Directional Trading"
      status="live"
      tagline="Predicts which way price will move and trades long or short on Binance futures."
      howItMakesMoney="An ML model scores every coin each candle; the bot opens trades in the predicted direction and exits on signal or stop."
      hero={hero}
      actions={<SubTabs tabs={SUB_TABS} active={sub} onChange={setSub} />}
    >
      {sub === "dashboard" && <Overview onNavigateTab={onNavigateTab} />}
      {sub === "trades" && <Trades />}
      {sub === "performance" && <Performance />}
      {sub === "signals" && <Signals />}
    </ModuleShell>
  );
}
