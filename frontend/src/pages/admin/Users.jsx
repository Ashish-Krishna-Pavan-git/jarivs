import { useEffect, useState } from "react";
import { RefreshCw, Users as UsersIcon } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header, Table } from "../../components/ui";

export function UsersPage() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [f, setF] = useState({ username: "", display_name: "", role: "user", password: "ChangeMe123!" });

  const load = () => {
    setError("");
    api("/api/admin/users")
      .then((d) => setRows(d.users || []))
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const create = () => {
    setError("");
    api("/api/admin/users", { method: "POST", body: JSON.stringify(f) })
      .then(() => {
        setF({ username: "", display_name: "", role: "user", password: "ChangeMe123!" });
        load();
      })
      .catch((e) => setError(e.message));
  };

  return (
    <section>
      <Header
        eyebrow="Access"
        title="User Management"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      <div className="panel form-grid">
        <Field label="Username">
          <input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
        </Field>
        <Field label="Display name">
          <input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} />
        </Field>
        <Field label="Role">
          <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            <option>user</option>
            <option>admin</option>
          </select>
        </Field>
        <Field label="Temporary password">
          <input value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <Button icon={UsersIcon} onClick={create}>
          Create User
        </Button>
      </div>
      <Table
        rows={rows}
        columns={[
          { label: "Username", key: "username" },
          { label: "Role", key: "role" },
          { label: "Must change", render: (r) => (r.must_change_password ? "Yes" : "No") },
          { label: "Active", render: (r) => (r.active ? "Yes" : "No") },
        ]}
      />
    </section>
  );
}