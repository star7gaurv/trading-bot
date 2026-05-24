import Card from "../components/Card";

export default function Overview() {
  return (
    <div className="space-y-4">
      <Card title="Overview" subtitle="At-a-glance state — coming in Increment 2">
        <p className="text-xs text-text-tertiary">
          This tab will hold the top stat row (P&L today/7d/30d, WR, open positions,
          regime, F&G), live trades mini-table, brain status, WF status, and a
          system-health summary card.
        </p>
      </Card>
    </div>
  );
}
