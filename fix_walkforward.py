import re

with open("dashboard-ui/src/tabs/WalkForward.jsx", "r") as f:
    content = f.read()

# Fix imports
if "useEffect" not in content:
    content = content.replace('import { useState } from "react";', 'import { useState, useEffect } from "react";')
if "getRunningFolds" not in content:
    content = content.replace('import { getWfLatest, getWfHistory } from "../api/client";', 'import { getWfLatest, getWfHistory, getRunningFolds } from "../api/client";')

# Define the correct LatestRun
new_latest = """function LatestRun({ data, error, loading, lastUpdated }) {
  const [runningData, setRunningData] = useState(null);

  // Poll running folds if an active run exists
  const isRunning = !!data?.active_run_name;
  useEffect(() => {
    let timer;
    async function poll() {
      if (isRunning) {
        try {
          const res = await getRunningFolds();
          if (res && res.available) {
            setRunningData(res);
          }
        } catch (e) {
          console.error("Failed to fetch running folds", e);
        }
      } else {
        setRunningData(null);
      }
      timer = setTimeout(poll, 15000);
    }
    poll();
    return () => clearTimeout(timer);
  }, [isRunning]);

  if (loading && !data) {
    return <Card title="Latest Walk-Forward" subtitle="Loading..." />;
  }

  if (error) {
    return (
      <Card title="Latest Walk-Forward" subtitle={<span className="text-loss">Error</span>}>
        <div className="p-4 text-sm text-text-secondary">{error.message || "Failed to load"}</div>
      </Card>
    );
  }

  if (!data?.available && !isRunning) {
    return (
      <Card title="Latest Walk-Forward" subtitle="No runs found">
        <div className="p-4 text-sm text-text-secondary">Walk-forward hasn't run yet.</div>
      </Card>
    );
  }

  const renderRunCard = (runName, summary, title, badgeProps, isLive) => {
    const agg = summary?.aggregate || {};
    const tradeCount = agg.total_trades;
    const totalPnl   = agg.total_profit_abs;
    
    return (
      <Card
        key={runName}
        title={title}
        subtitle={
          <span className="flex items-center gap-2">
            <span className="font-mono text-xxs truncate max-w-xs">{runName}</span>
            {badgeProps && (
              <Badge variant={badgeProps.variant} size="xs">
                {badgeProps.text}
              </Badge>
            )}
          </span>
        }
        lastUpdated={isLive ? new Date() : lastUpdated}
      >
        <div className="space-y-4 p-4">
          {summary ? (
            <>
              <GateRow agg={agg} />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1">
                <div className="bg-elevated border border-border rounded px-3 py-2">
                  <div className="text-xxs uppercase tracking-wider text-text-tertiary">Trades</div>
                  <div className="text-base font-mono text-text-primary mt-0.5">
                    {tradeCount ?? "—"}
                  </div>
                </div>
                <div className="bg-elevated border border-border rounded px-3 py-2">
                  <div className="text-xxs uppercase tracking-wider text-text-tertiary">P&L (USDT)</div>
                  <div
                    className={`text-base font-mono mt-0.5 ${
                      totalPnl == null ? "text-text-muted" : totalPnl >= 0 ? "text-profit" : "text-loss"
                    }`}
                  >
                    {totalPnl != null ? (totalPnl >= 0 ? "+" : "") + totalPnl.toFixed(2) : "—"}
                  </div>
                </div>
                {data.target_folds && (
                  <div className="bg-elevated border border-border rounded px-3 py-2">
                    <div className="text-xxs uppercase tracking-wider text-text-tertiary">Target Folds</div>
                    <div className="text-base font-mono text-text-primary mt-0.5">
                      {data.target_folds}
                    </div>
                  </div>
                )}
              </div>
              {summary.verdict && summary.verdict.length > 0 && (
                <div className="text-xs font-mono bg-elevated border border-border rounded p-3 text-text-secondary space-y-1">
                  {summary.verdict.map((v, i) => (
                    <div key={i} className={v.includes("✅") ? "text-profit" : "text-loss"}>
                      {v}
                    </div>
                  ))}
                </div>
              )}
              <div className="pt-2">
                <FoldTable data={{summary: summary}} />
              </div>
            </>
          ) : (
            <div className="text-sm text-text-secondary">Waiting for fold metrics to become available...</div>
          )}
        </div>
      </Card>
    );
  };

  const cards = [];

  // Active run card
  if (isRunning) {
    cards.push(
      renderRunCard(
        data.active_run_name,
        runningData,
        "Active Walk-Forward (Running)",
        { variant: "warn", text: "RUNNING" },
        true
      )
    );
  }

  // Previous completed run card
  if (data.summary) {
    cards.push(
      renderRunCard(
        data.name,
        data.summary,
        isRunning ? "Last Completed Walk-Forward" : "Latest Walk-Forward",
        { variant: data.summary.pass ? "ok" : "dead", text: data.summary.pass ? "PASS" : "FAIL" },
        false
      )
    );
  }

  return <div className="space-y-4">{cards}</div>;
}"""

# Extract everything up to function LatestRun
head = content.split("function LatestRun({ data, error, loading, lastUpdated }) {")[0]
# Extract everything from function FoldTable
tail = "function FoldTable" + content.split("function FoldTable")[1]

# Reassemble
with open("dashboard-ui/src/tabs/WalkForward.jsx", "w") as f:
    f.write(head + new_latest + "\n\n// ─── Fold metrics table ───────────────────────────────────────────────────────\n\n" + tail)

print("success")
