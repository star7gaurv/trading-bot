import Card from "../components/Card";

export default function SystemHealth() {
  return (
    <div className="space-y-4">
      <Card title="System Health" subtitle="Crons & processes — coming in Increment 2">
        <p className="text-xs text-text-tertiary">
          Full cron table with last-run + status + log tail, processes (FreqTrade,
          streamer, brain backtests), server stats (load/disk/memory), watchdog
          status + alert history.
        </p>
      </Card>
    </div>
  );
}
