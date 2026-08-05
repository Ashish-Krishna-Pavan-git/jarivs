import { useEffect, useState } from "react";
import { Activity, Database, Server, RefreshCw, Cpu, CheckCircle, AlertTriangle, Clock, ShieldAlert } from "lucide-react";
import { api } from "../../api";
import { Button, Header, Metric } from "../../components/ui";

export function Health() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    setLoading(true);
    api("/api/admin/system/overview")
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  };

  useEffect(load, []);

  if (loading) return <div className="muted" style={{ padding: "2rem" }}>Loading system health diagnostics...</div>;
  if (error) return <div className="error" style={{ padding: "2rem" }}>System Health Error: {error}</div>;

  const rt = data?.runtime || {};
  const sys = data?.system || {};
  const tel = data?.telemetry || {};
  const storage = data?.storage || {};

  return (
    <section className="health-dashboard">
      <Header
        eyebrow="System Observability"
        title="System Health & Infrastructure Diagnostics"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh Health
          </Button>
        }
      />

      <div className="metric-grid" style={{ marginBottom: "1.5rem" }}>
        <Metric
          icon={Activity}
          label="Scheduler Status"
          value={data?.scheduler_running ? "Active" : "Stopped"}
          hint={`Pipeline Phase: ${rt.phase || "Idle"}`}
        />
        <Metric
          icon={Database}
          label="Storage Persistence"
          value={storage.hf_storage_configured ? "HF Dataset Synced" : "Local Storage"}
          hint={storage.hf_storage_repo || "Persistent DB Active"}
        />
        <Metric
          icon={Cpu}
          label="Notification Provider"
          value={data?.notification_provider ? data.notification_provider.toUpperCase() : "SLACK"}
          hint={`Slack: ${data?.slack_enabled ? "Enabled" : "Disabled"} | Telegram: ${data?.telegram_enabled ? "Enabled" : "Disabled"}`}
        />
        <Metric
          icon={Clock}
          label="Last Cycle Execution"
          value={rt.last_cycle_at ? new Date(rt.last_cycle_at * 1000).toLocaleTimeString() : "Never"}
          hint={`Cycles Run: ${rt.cycle_count || 0}`}
        />
      </div>

      <div className="panel-grid">
        <div className="panel">
          <h3><Server size={18} /> Runtime Component Status</h3>
          <ul className="health-list" style={{ listStyle: "none", padding: 0, marginTop: "1rem" }}>
            <li style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border-color, #333)", display: "flex", justifyContent: "space-between" }}>
              <span>Database Engine (SQLite)</span>
              <span className="test-ok"><CheckCircle size={14} /> Operational</span>
            </li>
            <li style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border-color, #333)", display: "flex", justifyContent: "space-between" }}>
              <span>Background Scheduler Subprocess</span>
              {data?.scheduler_running ? (
                <span className="test-ok"><CheckCircle size={14} /> Running (PID {data?.scheduler_pid})</span>
              ) : (
                <span className="test-fail"><AlertTriangle size={14} /> Inactive</span>
              )}
            </li>
            <li style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border-color, #333)", display: "flex", justifyContent: "space-between" }}>
              <span>Slack Notification Delivery</span>
              {data?.slack_enabled ? (
                <span className="test-ok"><CheckCircle size={14} /> Ready</span>
              ) : (
                <span className="muted">Disabled</span>
              )}
            </li>
            <li style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border-color, #333)", display: "flex", justifyContent: "space-between" }}>
              <span>Telegram Bot Polling</span>
              {data?.telegram_enabled ? (
                <span className="test-ok"><CheckCircle size={14} /> Active</span>
              ) : (
                <span className="muted">Disabled by configuration</span>
              )}
            </li>
          </ul>
        </div>

        <div className="panel">
          <h3><ShieldAlert size={18} /> Telemetry & Exception Metrics</h3>
          <div style={{ marginTop: "1rem" }}>
            <p><strong>Articles Processed:</strong> {tel.articles_processed || 0}</p>
            <p><strong>Articles Scraped:</strong> {tel.articles_scraped || 0}</p>
            <p><strong>Daily Reports Generated:</strong> {tel.reports_generated || 0}</p>
            <p><strong>Audio Podcasts Built:</strong> {tel.audio_podcasts_generated || 0}</p>
            <p style={{ marginTop: "1rem", color: "var(--muted-color, #aaa)" }}>
              All system metrics are permanently stored in SQLite and automatically synced to Hugging Face Dataset when cloud storage is enabled.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
