import { useEffect, useState, useRef } from "react";
import { Activity, Brain, Play, RefreshCw, Rss, Users, Clock, Cpu, Zap, AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { api } from "../../api";
import { Button, Header, Metric } from "../../components/ui";

const PHASE_LABELS = {
  idle: "Idle",
  collecting: "Collecting sources",
  processing: "AI processing",
  digesting: "Generating digest",
  syncing: "Syncing storage",
  daily_summary: "Daily summary",
};

export function Dashboard() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const timerRef = useRef(null);

  const load = () => {
    setError("");
    api("/api/admin/overview")
      .then(setD)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  // Auto-refresh every 5 seconds so background work is visible without manual refresh
  useEffect(() => {
    if (!autoRefresh) return;
    timerRef.current = setInterval(load, 5000);
    return () => clearInterval(timerRef.current);
  }, [autoRefresh]);

  const runCycle = () => {
    setBusy(true);
    api("/api/admin/run/cycle", { method: "POST" })
      .then(() => {
        setBusy(false);
        setTimeout(load, 1000);
      })
      .catch((e) => {
        setBusy(false);
        setError(e.message);
      });
  };

  const ai = d?.ai_status || {};
  const rt = d?.runtime || {};
  const q = d?.queue || {};
  const tel = d?.telemetry || {};
  const phaseLabel = PHASE_LABELS[rt.phase] || rt.phase || "Idle";

  return (
    <section>
      <Header
        eyebrow="Control plane"
        title="Dashboard"
        actions={
          <>
            <Button
              icon={RefreshCw}
              variant="secondary"
              onClick={() => {
                setAutoRefresh(!autoRefresh);
                load();
              }}
            >
              {autoRefresh ? "Auto 5s" : "Manual"}
            </Button>
            <Button icon={Play} onClick={runCycle} disabled={busy}>
              {busy ? "Starting..." : "Run Cycle"}
            </Button>
          </>
        }
      />
      {error && <p className="error">{error}</p>}

      {/* Phase banner */}
      <div className={`phase-banner phase-${rt.phase || "idle"}`}>
        <Activity size={20} />
        <div>
          <strong>{phaseLabel}</strong>
          {rt.current_cycle_slot && <span> · Cycle {rt.current_cycle_number} ({rt.current_cycle_slot})</span>}
          {rt.next_cycle_at_ist && rt.phase === "idle" && <span> · Next: {rt.next_cycle_at_ist}</span>}
        </div>
      </div>

      {/* Core metrics */}
      <div className="metric-grid">
        <Metric icon={Activity} label="Phase" value={phaseLabel} />
        <Metric icon={Brain} label="Processed" value={tel.total_processed || 0} />
        <Metric icon={Rss} label="Sources" value={d?.sources ?? 0} />
        <Metric icon={Users} label="Users" value={d?.users ?? 0} />
      </div>

      {/* Queue progress */}
      <div className="panel">
        <h2>Queue Progress</h2>
        <div className="metric-grid">
          <Metric icon={Clock} label="Pending" value={q.pending || 0} />
          <Metric icon={Cpu} label="Processing" value={q.processing || 0} />
          <Metric icon={CheckCircle} label="Done" value={q.done || 0} />
          <Metric icon={XCircle} label="Failed" value={q.failed || 0} />
        </div>
        {q.total > 0 && (
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${Math.round(((q.done || 0) / q.total) * 100)}%` }}
            />
            <span>{Math.round(((q.done || 0) / q.total) * 100)}%</span>
          </div>
        )}
      </div>

      {/* AI status */}
      <div className="panel">
        <h2>AI Analysis Status</h2>
        {ai.last_called_at ? (
          <div className="ai-status-grid">
            <div><span className="muted">Provider</span><strong>{ai.last_provider || "—"}</strong></div>
            <div><span className="muted">Model</span><strong>{ai.last_model || "—"}</strong></div>
            <div><span className="muted">Task</span><strong>{ai.last_task || "—"}</strong></div>
            <div><span className="muted">Latency</span><strong>{ai.last_latency_ms != null ? `${ai.last_latency_ms}ms` : "—"}</strong></div>
            <div>
              <span className="muted">Status</span>
              <strong className={ai.last_success ? "ok" : "err"}>
                {ai.last_success ? "✓ Success" : "✗ Failed"}
              </strong>
            </div>
            <div>
              <span className="muted">Fallback</span>
              <strong className={ai.last_fallback_used ? "warn" : ""}>
                {ai.last_fallback_used ? "Yes (fallback used)" : "No (primary)"}
              </strong>
            </div>
            <div><span className="muted">Last call</span><strong>{ai.last_called_at || "—"}</strong></div>
            <div><span className="muted">Total calls</span><strong>{ai.total_calls || 0}</strong></div>
            <div><span className="muted">Fallbacks</span><strong>{ai.total_fallbacks || 0}</strong></div>
            <div><span className="muted">Failures</span><strong>{ai.total_failures || 0}</strong></div>
          </div>
        ) : (
          <p className="muted">No AI calls yet. Run a cycle to see analysis status.</p>
        )}
        {ai.last_error && (
          <p className="error">
            <AlertTriangle size={14} /> Last error: {ai.last_error}
          </p>
        )}
      </div>

      {/* Telemetry by severity */}
      <div className="panel">
        <h2>Telemetry</h2>
        <div className="metric-grid">
          <Metric icon={Zap} label="Cycles" value={tel.cycles_run || 0} />
          <Metric icon={Brain} label="Scraped" value={tel.total_scraped || 0} />
          <Metric icon={XCircle} label="Failed" value={tel.total_failed || 0} />
          <Metric icon={Clock} label="Last cycle" value={tel.last_cycle_at ? new Date(tel.last_cycle_at).toLocaleString() : "Never"} />
        </div>
        {tel.by_severity && (
          <div className="severity-grid">
            {Object.entries(tel.by_severity).map(([sev, count]) => (
              <span key={sev} className={`sev-badge sev-${sev.toLowerCase()}`}>{sev}: {count}</span>
            ))}
          </div>
        )}
      </div>

      {/* Cycle timing */}
      <div className="panel">
        <h2>Cycle Timing</h2>
        <div className="metric-grid">
          <Metric icon={Clock} label="Last started" value={rt.last_cycle_started_at || "—"} />
          <Metric icon={Clock} label="Last finished" value={rt.last_cycle_finished_at || "—"} />
          <Metric icon={Clock} label="Last daily" value={rt.last_daily_run_ist || "—"} />
          <Metric icon={Clock} label="Next cycle" value={rt.next_cycle_at_ist || "—"} />
        </div>
      </div>
    </section>
  );
}