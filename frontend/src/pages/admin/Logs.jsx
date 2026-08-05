import { useEffect, useState } from "react";
import { RefreshCw, Search, Copy, CheckCircle, Download } from "lucide-react";
import { api } from "../../api";
import { Button, Header, Table } from "../../components/ui";

export function Logs() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [component, setComponent] = useState("");
  const [copied, setCopied] = useState(false);

  const load = () => {
    setError("");
    let url = `/api/admin/logs?limit=500&level=${level}&q=${encodeURIComponent(q)}`;
    if (component) {
      url += `&component=${component}`;
    }
    api(url)
      .then((d) => setRows(d.logs || []))
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const copyLogs = () => {
    const text = rows.map((r) => `[${r.created_at}] [${r.level}] [${r.component}] ${r.message}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const exportLogs = () => {
    const jsonStr = JSON.stringify(rows, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `jarvis_logs_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section>
      <Header
        eyebrow="Observability & Auditing"
        title="System Event & Error Logs"
        actions={
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Button icon={copied ? CheckCircle : Copy} variant="secondary" onClick={copyLogs}>
              {copied ? "Copied!" : "Copy Logs"}
            </Button>
            <Button icon={Download} variant="secondary" onClick={exportLogs}>
              Export JSON
            </Button>
            <Button icon={RefreshCw} variant="secondary" onClick={load}>
              Refresh Logs
            </Button>
          </div>
        }
      />
      {error && <p className="error">{error}</p>}

      <div className="toolbar" style={{ gap: "0.75rem", flexWrap: "wrap", marginBottom: "1rem" }}>
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">All Severity Levels</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>

        <select value={component} onChange={(e) => setComponent(e.target.value)}>
          <option value="">All Components</option>
          <option value="notifier">Notifier</option>
          <option value="slack">Slack</option>
          <option value="telegram">Telegram</option>
          <option value="severity_engine">Severity Engine</option>
          <option value="scheduler">Scheduler</option>
          <option value="collector">Collector</option>
          <option value="wordpress">WordPress</option>
          <option value="mcp">MCP</option>
          <option value="config">Config</option>
        </select>

        <input
          placeholder="Search log messages..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ flexGrow: 1, minWidth: "200px" }}
        />

        <Button icon={Search} onClick={load}>
          Filter
        </Button>
      </div>

      <Table
        rows={rows}
        columns={[
          {
            label: "Timestamp",
            render: (r) => <span className="muted">{new Date(r.created_at).toLocaleString()}</span>,
          },
          {
            label: "Level",
            render: (r) => (
              <span
                style={{
                  fontWeight: 600,
                  padding: "0.15rem 0.4rem",
                  borderRadius: "4px",
                  fontSize: "0.8rem",
                  backgroundColor: r.level === "ERROR" ? "rgba(239, 68, 68, 0.2)" : r.level === "WARN" ? "rgba(245, 158, 11, 0.2)" : "rgba(16, 185, 129, 0.2)",
                  color: r.level === "ERROR" ? "#ef4444" : r.level === "WARN" ? "#f59e0b" : "#10b981",
                }}
              >
                {r.level}
              </span>
            ),
          },
          { label: "Component", key: "component" },
          { label: "Message", key: "message" },
        ]}
        empty="No event logs match the selected filter criteria"
      />
    </section>
  );
}