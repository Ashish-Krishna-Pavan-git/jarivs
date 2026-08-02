import { useEffect, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { api } from "../../api";
import { Button, Header, Table } from "../../components/ui";

export function Logs() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");

  const load = () => {
    setError("");
    api(`/api/admin/logs?limit=500&level=${level}&q=${encodeURIComponent(q)}`)
      .then((d) => setRows(d.logs || []))
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  return (
    <section>
      <Header
        eyebrow="Observability"
        title="Logs"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      <div className="toolbar">
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">All levels</option>
          <option>INFO</option>
          <option>WARN</option>
          <option>ERROR</option>
        </select>
        <input placeholder="Search logs" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button icon={Search} onClick={load}>
          Filter
        </Button>
      </div>
      <Table
        rows={rows}
        columns={[
          { label: "Time", key: "created_at" },
          { label: "Level", key: "level" },
          { label: "Component", key: "component" },
          { label: "Message", key: "message" },
        ]}
      />
    </section>
  );
}