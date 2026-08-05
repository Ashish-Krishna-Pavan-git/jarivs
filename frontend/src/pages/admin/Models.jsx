import { useEffect, useState } from "react";
import { Brain, RefreshCw, AlertTriangle, CheckCircle, Zap, ShieldAlert, Cpu } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header, Table } from "../../components/ui";

export function Models() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [freeOnly, setFreeOnly] = useState(true);
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
    api("/api/admin/models/summary")
      .then((d) => {
        setSummary(d);
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

  const allProviders = summary?.providers || [];
  const displayedProviders = freeOnly ? allProviders.filter((p) => p.is_free) : allProviders;

  return (
    <section>
      <Header
        eyebrow="AI Routing & Models"
        title="AI Model Provider Management"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh Models
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}

      {summary && (
        <div className="metric-grid" style={{ marginBottom: "1.5rem" }}>
          <div>
            <span className="muted">Total Configured Models</span>
            <h3>{summary.total_models || 0}</h3>
          </div>
          <div>
            <span className="muted">Free Tier Models</span>
            <h3 style={{ color: "#10b981" }}>{summary.free_models || 0}</h3>
          </div>
          <div>
            <span className="muted">Active Model Routes</span>
            <h3>{summary.active_models || 0}</h3>
          </div>
          <div>
            <span className="muted">Rate-Limited Cooldowns</span>
            <h3 style={{ color: summary.rate_limited_models > 0 ? "#f59e0b" : "inherit" }}>
              {summary.rate_limited_models || 0}
            </h3>
          </div>
        </div>
      )}

      <div className="panel-grid" style={{ marginBottom: "1.5rem" }}>
        <div className="panel">
          <h3><Zap size={18} /> Groq LPU Cloud (Free Tier)</h3>
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.9rem" }}>
            Used for ultra-fast, low-latency article classification, severity assignment, and entity extraction.
          </p>
          <p className="muted" style={{ fontSize: "0.85rem" }}>⚡ 30 RPM limit (2.5s minimum interval between requests)</p>
        </div>

        <div className="panel">
          <h3><Brain size={18} /> Google Gemini AI (Free Tier)</h3>
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.9rem" }}>
            Used for deep analytical reasoning, executive daily digest synthesis, and newsletter generation.
          </p>
          <p className="muted" style={{ fontSize: "0.85rem" }}>🧠 15 RPM limit (4.5s minimum interval between requests)</p>
        </div>

        <div className="panel">
          <h3><Cpu size={18} /> Future: Ollama & OpenRouter</h3>
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.9rem" }}>
            Placeholders configured for zero-cloud-cost local hardware inference (Ollama) and multi-model cloud routing (OpenRouter).
          </p>
        </div>
      </div>

      <div className="toolbar" style={{ marginBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <label className="check" style={{ fontSize: "0.95rem" }}>
          <input
            type="checkbox"
            checked={freeOnly}
            onChange={(e) => setFreeOnly(e.target.checked)}
          />{" "}
          Show Free Tier Models Only
        </label>
        <span className="muted" style={{ fontSize: "0.85rem" }}>
          Showing {displayedProviders.length} of {allProviders.length} providers
        </span>
      </div>

      <Table
        rows={displayedProviders}
        columns={[
          { label: "Provider Name", key: "name" },
          { label: "Type", key: "provider_type" },
          { label: "Model", key: "model" },
          {
            label: "Tier",
            render: (r) => (
              <span style={{ color: r.is_free ? "#10b981" : "#f59e0b", fontWeight: 600 }}>
                {r.is_free ? "Free Tier" : "Paid Tier"}
              </span>
            ),
          },
          {
            label: "Status",
            render: (r) =>
              r.placeholder ? (
                <span className="muted">Future Placeholder</span>
              ) : r.cooldown_remaining_sec > 0 ? (
                <span className="test-warn">
                  <AlertTriangle size={12} /> Cooldown ({r.cooldown_remaining_sec}s)
                </span>
              ) : r.enabled ? (
                <span className="test-ok">
                  <CheckCircle size={12} /> Active
                </span>
              ) : (
                <span className="muted">Disabled</span>
              ),
          },
          {
            label: "Best For",
            render: (r) => <span className="muted" style={{ fontSize: "0.85rem" }}>{r.guide?.best_for}</span>,
          },
        ]}
        empty="No model providers match the selected filter"
      />

      <div className="panel form-grid" style={{ marginTop: "1.5rem" }}>
        <h3>Add Custom AI Provider</h3>
        <Field label="Name">
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Local Ollama Phi-4" />
        </Field>
        <Field label="Type">
          <select
            value={f.provider_type}
            onChange={(e) => setF({ ...f, provider_type: e.target.value })}
          >
            <option value="gemini">Gemini</option>
            <option value="groq">Groq</option>
            <option value="ollama">Ollama (Local)</option>
            <option value="openai_compatible">OpenAI Compatible / OpenRouter</option>
          </select>
        </Field>
        <Field label="Model Identifier">
          <input value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} placeholder="e.g. llama-3.3-70b-versatile" />
        </Field>
        <Field label="Base URL (Optional)">
          <input value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} placeholder="http://localhost:11434" />
        </Field>
        <Field label="API Key Environment Variable">
          <input value={f.api_key_env} onChange={(e) => setF({ ...f, api_key_env: e.target.value })} placeholder="GROQ_API_KEY" />
        </Field>
        <Field label="Minimum Interval (seconds)">
          <input
            type="number"
            value={f.min_interval}
            onChange={(e) => setF({ ...f, min_interval: e.target.value })}
          />
        </Field>
        <Button icon={Brain} onClick={save}>
          Save Model Provider
        </Button>
      </div>
    </section>
  );
}