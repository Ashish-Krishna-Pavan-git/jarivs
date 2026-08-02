import { useEffect, useState } from "react";
import { Brain, RefreshCw, AlertTriangle, CheckCircle } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header, Table } from "../../components/ui";

export function Models() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({
    name: "",
    provider_type: "openai_compatible",
    model: "",
    base_url: "",
    api_key_env: "",
    min_interval: 0,
    enabled: true,
  });

  const load = () => {
    setError("");
    setLoading(true);
    api("/api/admin/models")
      .then((d) => {
        setRows(d.providers || []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  };

  useEffect(load, []);

  const save = () => {
    setError("");
    api("/api/admin/models", { method: "POST", body: JSON.stringify(f) })
      .then(() => {
        setF({
          name: "",
          provider_type: "openai_compatible",
          model: "",
          base_url: "",
          api_key_env: "",
          min_interval: 0,
          enabled: true,
        });
        load();
      })
      .catch((e) => setError(e.message));
  };

  return (
    <section>
      <Header
        eyebrow="AI routing"
        title="AI Model Management"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      <div className="panel form-grid">
        <Field label="Name">
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <Field label="Type">
          <select
            value={f.provider_type}
            onChange={(e) => setF({ ...f, provider_type: e.target.value })}
          >
            <option>gemini</option>
            <option>groq</option>
            <option>ollama</option>
            <option>openai_compatible</option>
          </select>
        </Field>
        <Field label="Model">
          <input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} />
        </Field>
        <Field label="Base URL">
          <input value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} />
        </Field>
        <Field label="API Key Env">
          <input value={f.api_key_env} onChange={(e) => setF({ ...f, api_key_env: e.target.value })} />
        </Field>
        <Field label="Min Interval">
          <input
            type="number"
            value={f.min_interval}
            onChange={(e) => setF({ ...f, min_interval: e.target.value })}
          />
        </Field>
        <label className="check">
          <input
            type="checkbox"
            checked={f.enabled}
            onChange={(e) => setF({ ...f, enabled: e.target.checked })}
          />{" "}
          Enabled
        </label>
        <Button icon={Brain} onClick={save}>
          Save Provider
        </Button>
      </div>
      {loading ? (
        <p className="muted">Loading models...</p>
      ) : (
        <Table
          rows={rows}
          columns={[
            { label: "Name", key: "name" },
            { label: "Type", key: "provider_type" },
            { label: "Model", key: "model" },
            { label: "Enabled", render: (r) => (r.enabled ? "Yes" : "No") },
            {
              label: "Status",
              render: (r) =>
                r.blocked_until ? (
                  <span className="test-fail">
                    <AlertTriangle size={12} /> Blocked until {r.blocked_until}
                  </span>
                ) : r.enabled ? (
                  <span className="test-ok">
                    <CheckCircle size={12} /> Active
                  </span>
                ) : (
                  <span className="muted">Disabled</span>
                ),
            },
          ]}
          empty="No model providers configured"
        />
      )}
    </section>
  );
}