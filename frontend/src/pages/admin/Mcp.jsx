import { useEffect, useState } from "react";
import { Link2, RefreshCw, Activity, Cpu, CheckCircle, AlertTriangle, Play } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header, Table } from "../../components/ui";

export function Mcp() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [auditResult, setAuditResult] = useState(null);
  const [auditing, setAuditing] = useState(false);
  const [f, setF] = useState({ name: "", transport: "http", endpoint: "", enabled: true, args: "" });

  const load = () => {
    setError("");
    api("/api/admin/mcp")
      .then((d) => setRows(d.servers || []))
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const save = () => {
    setError("");
    setNotice("");
    api("/api/admin/mcp", {
      method: "POST",
      body: JSON.stringify({
        ...f,
        config:
          f.transport === "stdio"
            ? { command: f.endpoint, args: f.args.split(" ").filter(Boolean), timeout_seconds: 20 }
            : { allow_private_network: false },
      }),
    })
      .then(() => {
        setF({ name: "", transport: "http", endpoint: "", enabled: true, args: "" });
        load();
      })
      .catch((e) => setError(e.message));
  };

  const test = (id) => {
    setError("");
    setNotice("");
    api(`/api/admin/mcp/${id}/test`, { method: "POST" })
      .then((d) => setNotice(d.ok ? "MCP test passed" : d.error || "MCP test failed"))
      .catch((e) => setError(e.message));
  };

  const runAudit = () => {
    setError("");
    setAuditing(true);
    api("/api/admin/mcp/source-audit", { method: "POST" })
      .then((res) => {
        setAuditResult(res);
        setAuditing(false);
      })
      .catch((e) => {
        setError(e.message);
        setAuditing(false);
      });
  };

  return (
    <section>
      <Header
        eyebrow="Model Context Protocol"
        title="MCP Integrations & Source Auditing"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      {notice && <p className="muted">{notice}</p>}

      <div className="panel" style={{ marginBottom: "1.5rem" }}>
        <h3><Cpu size={18} /> Model Context Protocol (MCP) Overview</h3>
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          Model Context Protocol enables JARVIS AI components to interface safely with external tools, local command-line utilities (STDIO), and remote HTTP microservices to audit RSS feeds, inspect content freshness, and detect category drift.
        </p>
        <div style={{ marginTop: "1rem" }}>
          <Button icon={Play} onClick={runAudit} disabled={auditing}>
            {auditing ? "Auditing RSS Sources..." : "Run Built-in MCP Source Audit"}
          </Button>
        </div>
      </div>

      {auditResult && (
        <div className="panel" style={{ marginBottom: "1.5rem", borderLeft: "4px solid var(--color-primary, #3b82f6)" }}>
          <h3><Activity size={18} /> MCP Source Audit Diagnostic</h3>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Audited at: {new Date(auditResult.audited_at).toLocaleString()}
          </p>

          <div className="metric-grid" style={{ marginTop: "1rem", marginBottom: "1rem" }}>
            <div>
              <span className="muted">Total Sources</span>
              <h4>{auditResult.summary?.total_sources || 0}</h4>
            </div>
            <div>
              <span className="muted">Healthy Feeds</span>
              <h4 style={{ color: "#10b981" }}>{auditResult.summary?.healthy_sources || 0}</h4>
            </div>
            <div>
              <span className="muted">Stale Feeds (&gt;72h)</span>
              <h4 style={{ color: "#f59e0b" }}>{auditResult.summary?.stale_sources || 0}</h4>
            </div>
            <div>
              <span className="muted">Duplicate Rate (48h)</span>
              <h4>{auditResult.summary?.duplicate_rate_pct || 0}%</h4>
            </div>
          </div>

          <Table
            rows={auditResult.sources || []}
            columns={[
              { label: "Source Name", key: "name" },
              { label: "Category", key: "category" },
              {
                label: "Status",
                render: (r) => (
                  <span className={r.ok ? (r.freshness_hours > 72 ? "test-warn" : "test-ok") : "test-fail"}>
                    {r.ok ? (r.freshness_hours > 72 ? "⚠️ Stale (>72h)" : "✓ Healthy") : `✗ ${r.status}`}
                  </span>
                ),
              },
              { label: "HTTP Latency", render: (r) => (r.latency_ms ? `${r.latency_ms} ms` : "N/A") },
              { label: "Feed Items", key: "feed_items" },
              { label: "Freshness", render: (r) => (r.freshness_hours ? `${r.freshness_hours}h ago` : "Unknown") },
            ]}
          />
        </div>
      )}

      <div className="panel form-grid" style={{ marginBottom: "1.5rem" }}>
        <h3>Register Custom MCP Server</h3>
        <Field label="Name">
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. RSS Audit Agent" />
        </Field>
        <Field label="Transport">
          <select value={f.transport} onChange={(e) => setF({ ...f, transport: e.target.value })}>
            <option value="http">HTTP Endpoint</option>
            <option value="stdio">STDIN/STDOUT Command</option>
          </select>
        </Field>
        <Field label={f.transport === "http" ? "Endpoint URL" : "Executable Command"}>
          <input value={f.endpoint} onChange={(e) => setF({ ...f, endpoint: e.target.value })} placeholder={f.transport === "http" ? "https://mcp.local/api" : "python -m mcp_tool"} />
        </Field>
        {f.transport === "stdio" && (
          <Field label="Command Arguments">
            <input value={f.args} onChange={(e) => setF({ ...f, args: e.target.value })} placeholder="--config /tmp/mcp.json" />
          </Field>
        )}
        <Button icon={Link2} onClick={save}>
          Save MCP Server
        </Button>
      </div>

      <Table
        rows={rows}
        columns={[
          { label: "Name", key: "name" },
          { label: "Transport", key: "transport" },
          { label: "Endpoint / Command", key: "endpoint" },
          { label: "Enabled", render: (r) => (r.enabled ? "Yes" : "No") },
          {
            label: "Action",
            render: (r) => <Button onClick={() => test(r.id)}>Test Server</Button>,
          },
        ]}
        empty="No custom external MCP servers registered"
      />
    </section>
  );
}