import { useEffect, useState } from "react";
import { RefreshCw, Rss } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header, Table } from "../../components/ui";

export function Sources() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({ name: "", url: "", category: "tech", enabled: true });

  const load = () => {
    setError("");
    setLoading(true);
    api("/api/admin/sources")
      .then((d) => {
        setRows(d.sources || []);
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
    api("/api/admin/sources", { method: "POST", body: JSON.stringify(f) })
      .then(() => {
        setF({ name: "", url: "", category: "tech", enabled: true });
        load();
      })
      .catch((e) => setError(e.message));
  };

  const remove = (id) => {
    setError("");
    api(`/api/admin/sources/${id}`, { method: "DELETE" })
      .then(load)
      .catch((e) => setError(e.message));
  };

  return (
    <section>
      <Header
        eyebrow="Collectors"
        title="Source Management"
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
        <Field label="URL">
          <input value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
        </Field>
        <Field label="Category">
          <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            <option>cybersec</option>
            <option>ai</option>
            <option>tech</option>
            <option>mobile</option>
            <option>hardware</option>
            <option>newsletter</option>
            <option>business</option>
          </select>
        </Field>
        <label className="check">
          <input
            type="checkbox"
            checked={f.enabled}
            onChange={(e) => setF({ ...f, enabled: e.target.checked })}
          />{" "}
          Enabled
        </label>
        <Button icon={Rss} onClick={save}>
          Save
        </Button>
      </div>
      {loading ? (
        <p className="muted">Loading sources...</p>
      ) : (
        <Table
          rows={rows}
          columns={[
            { label: "Name", key: "name" },
            { label: "Category", key: "category" },
            { label: "Enabled", render: (r) => (r.enabled ? "Yes" : "No") },
            {
              label: "URL",
              render: (r) => <code>{r.url}</code>,
            },
            {
              label: "Action",
              render: (r) => (
                <Button variant="danger" onClick={() => remove(r.id)}>
                  Delete
                </Button>
              ),
            },
          ]}
          empty="No sources configured"
        />
      )}
    </section>
  );
}