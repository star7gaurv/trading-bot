import Card from "../components/Card";

export default function Performance() {
  return (
    <div className="space-y-4">
      <Card title="Performance" subtitle="P&L, charts, per-pair — coming in Increment 3">
        <p className="text-xs text-text-tertiary">
          Cumulative P&L chart (TradingView lightweight-charts), daily/weekly/monthly
          tables, per-pair bar chart, per-regime breakdown, WR over time.
        </p>
      </Card>
    </div>
  );
}
