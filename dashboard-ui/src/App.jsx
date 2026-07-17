import { useEffect, useState } from "react";
import {
  TrendingUp,
  Coins,
  ArrowLeftRight,
  Grid3x3,
  Scale,
  Brain as BrainIcon,
  Repeat,
  Server,
  Settings as SettingsIcon,
} from "lucide-react";

import Layout from "./components/Layout";
import LoginGate from "./components/LoginGate";
import { getToken, whoami } from "./api/client";

import DirectionalModule from "./tabs/modules/Directional";
import FundingFarmModule from "./tabs/modules/FundingFarm";
import PairsTradingModule from "./tabs/modules/PairsTrading";
import GridTradingModule from "./tabs/modules/GridTrading";
import ArbitrageModule from "./tabs/modules/Arbitrage";
import Brain from "./tabs/Brain";
import WalkForward from "./tabs/WalkForward";
import SystemHealth from "./tabs/SystemHealth";
import Settings from "./tabs/Settings";

// Two-group nav: "Modules" are the sellable trading products (each with a
// Live/Paper/Soon status); "System" is the shared engine room.
const TABS = [
  { id: "directional", label: "Directional", icon: TrendingUp, group: "Modules", status: "live", Component: DirectionalModule },
  { id: "funding", label: "Funding Farm", icon: Coins, group: "Modules", status: "paper", Component: FundingFarmModule },
  { id: "pairs", label: "Pairs Trading", icon: ArrowLeftRight, group: "Modules", status: "paper", Component: PairsTradingModule },
  { id: "grid", label: "Grid Trading", icon: Grid3x3, group: "Modules", status: "paper", Component: GridTradingModule },
  { id: "arbitrage", label: "Arbitrage", icon: Scale, group: "Modules", status: "paper", Component: ArbitrageModule },
  { id: "brain", label: "Brain", icon: BrainIcon, group: "System", Component: Brain },
  { id: "wf", label: "Walk-Forward", icon: Repeat, group: "System", Component: WalkForward },
  { id: "system", label: "System Health", icon: Server, group: "System", Component: SystemHealth },
  { id: "settings", label: "Settings", icon: SettingsIcon, group: "System", Component: Settings },
];

// Persist active tab in URL hash so refresh / share keeps you on the same tab.
// Legacy hashes from the old flat-tab layout map onto the new module layout.
const LEGACY_HASH_MAP = {
  overview: "directional",
  trades: "directional",
  signals: "directional",
  performance: "directional",
};

function readTabFromHash() {
  const h = window.location.hash.replace(/^#\/?/, "");
  if (TABS.find((t) => t.id === h)) return h;
  if (LEGACY_HASH_MAP[h]) return LEGACY_HASH_MAP[h];
  return "directional";
}

function writeTabToHash(id) {
  if (window.location.hash !== `#${id}`) {
    window.history.replaceState(null, "", `#${id}`);
  }
}

export default function App() {
  // ─ auth state ─
  const [authed, setAuthed] = useState(() => Boolean(getToken()));
  const [verifying, setVerifying] = useState(authed);

  // Verify token on mount — handles the "token still in localStorage but server
  // restarted and forgot the secret" case
  useEffect(() => {
    if (!authed) return;
    let alive = true;
    whoami()
      .then(() => alive && setAuthed(true))
      .catch(() => alive && setAuthed(false))
      .finally(() => alive && setVerifying(false));
    return () => {
      alive = false;
    };
  }, [authed]);

  // Listen for 401s from API client → kicks back to login
  useEffect(() => {
    const handler = () => setAuthed(false);
    window.addEventListener("finbuddy:auth:expired", handler);
    return () => window.removeEventListener("finbuddy:auth:expired", handler);
  }, []);

  // ─ tab state ─
  const [activeTab, setActiveTab] = useState(readTabFromHash);
  useEffect(() => {
    const onHash = () => setActiveTab(readTabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const handleTabChange = (id) => {
    setActiveTab(id);
    writeTabToHash(id);
  };

  // ─ render gates ─
  if (verifying) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center text-text-tertiary text-xs">
        Verifying session…
      </div>
    );
  }

  if (!authed) {
    return <LoginGate onAuthed={() => setAuthed(true)} />;
  }

  const ActiveComponent = TABS.find((t) => t.id === activeTab)?.Component || DirectionalModule;

  return (
    <Layout tabs={TABS} activeTab={activeTab} onTabChange={handleTabChange}>
      <ActiveComponent onNavigateTab={handleTabChange} />
    </Layout>
  );
}
