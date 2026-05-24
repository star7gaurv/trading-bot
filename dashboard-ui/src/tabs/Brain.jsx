import Card from "../components/Card";

export default function Brain() {
  return (
    <div className="space-y-4">
      <Card title="Brain" subtitle="Autonomous hypothesis engine — coming in Increment 4">
        <p className="text-xs text-text-tertiary">
          Queue depth, recent experiment results, promotion candidates with config
          diff, and the brain log stream (reused from /ws/brain).
        </p>
      </Card>
    </div>
  );
}
