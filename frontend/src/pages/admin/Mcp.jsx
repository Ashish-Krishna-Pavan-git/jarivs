import { useEffect, useState } from "react";
import { Link2, RefreshCw } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header, Table } from "../../components/ui";

export function Mcp() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
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

  return (
    <section>
      <Header
        eyebrow="Tool context"
        title="MCP Servers"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      {notice && <p className="muted">{notice}</p>}
      <div className="panel form-grid">
        <Field label="Name">
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <Field label="Transport">
          <select value={f.transport} onChange={(e) => setF({ ...f, transport: e.target.value })}>
            <option value="http">HTTP</option>
            <option value="stdio">STDIN/STDOUT</option>
          </select>
        </Field>
        <Field label={f.transport === "http" ? "Endpoint" : "Command"}>
          <input value={f.endpoint} onChange={(e) => setF({ ...f, endpoint: e.target.value })} />
        </Field>
        {f.transport === "stdio" && (
          <Field label="Args">
            <input value={f.args} onChange={(e) => setF({ ...f, args: e.target.value })} />
          </Field>
        )}
        <Button icon={Link2} onClick={save}>
          Save MCP
        </Button>
      </div>
      <Table
        rows={rows}
        columns={[
          { label: "Name", key: "name" },
          { label: "Transport", key: "transport" },
          { label: "Endpoint", key: "endpoint" },
          { label: "Enabled", render: (r) => (r.enabled ? "Yes" : "No") },
          {
            label: "Test",
            render: (r) => <Button onClick={() => test(r.id)}>Test</Button>,
          },
        ]}
      />
    </section>
  );
}