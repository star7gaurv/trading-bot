import Card from "../components/Card";

export default function Settings() {
  return (
    <div className="space-y-4">
      <Card title="Settings" subtitle="View-only config — coming in Increment 5">
        <p className="text-xs text-text-tertiary">
          Current env vars, pair_whitelist, FreqAI identifier, live thresholds.
          Future: edit + restart with confirmation.
        </p>
      </Card>
    </div>
  );
}
