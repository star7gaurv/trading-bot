import Card from "../components/Card";

export default function WalkForward() {
  return (
    <div className="space-y-4">
      <Card title="Walk-Forward" subtitle="Validation — coming in Increment 4">
        <p className="text-xs text-text-tertiary">
          Latest run header with PASS/FAIL gates (WR &gt; 50, Sharpe &gt; 0.5, DD &lt; 20,
          PF &gt; 1.2), fold-by-fold metrics, historical runs list, trend chart.
        </p>
      </Card>
    </div>
  );
}
