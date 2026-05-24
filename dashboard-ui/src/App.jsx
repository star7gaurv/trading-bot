import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  TrendingUp,
  LineChart,
  Brain as BrainIcon,
  Repeat,
  Server,
  Settings as SettingsIcon,
} from "lucide-react";

import Layout from "./components/Layout";
import LoginGate from "./components/LoginGate";
import { getToken, whoami } from "./api/client";

import Overview from "./tabs/Overview";
import Trades from "./tabs/Trades";
import Performance from "./tabs/Performance";
import Brain from "./tabs/Brain";
import WalkForward from "./tabs/WalkForward";
import SystemHealth from "./tabs/SystemHealth";
import Settings from "./tabs/Settings";

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, Component: Overview },
  { id: "trades", label: "Trades", icon: TrendingUp, Component: Trades },
  { id: "performance", label: "Performance", icon: LineChart, Component: Performance },
  { id: "brain", label: "Brain", icon: BrainIcon, Component: Brain },
  { id: "wf", label: "Walk-Forward", icon: Repeat, Component: WalkForward },
  { id: "system", label: "System Health", icon: Server, Component: SystemHealth },
  { id: "settings", label: "Settings", icon: SettingsIcon, Component: Settings },
];

// Persist active tab in URL hash so refresh / share keeps you on the same tab
function readTabFromHash() {
  const h = window.location.hash.replace(/^#\/?/, "");
  return TABS.find((t) => t.id === h)?.id || "overview";
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

  const ActiveComponent = TABS.find((t) => t.id === activeTab)?.Component || Overview;

  return (
    <Layout tabs={TABS} activeTab={activeTab} onTabChange={handleTabChange}>
      <ActiveComponent />
    </Layout>
  );
}
