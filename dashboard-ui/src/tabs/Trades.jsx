import Card from "../components/Card";

export default function Trades() {
  return (
    <div className="space-y-4">
      <Card title="Trades" subtitle="Open + closed history — coming in Increment 3">
        <p className="text-xs text-text-tertiary">
          Will mirror FreqTrade: open trades table with force-exit, closed trades
          (paginated + filterable), per-pair performance, trade detail drawer.
        </p>
      </Card>
    </div>
  );
}
