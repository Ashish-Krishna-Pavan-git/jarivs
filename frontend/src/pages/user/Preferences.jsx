import { useEffect, useState } from "react";
import { Settings } from "lucide-react";
import { api } from "../../api";
import { Button, Field, Header } from "../../components/ui";

export function Preferences() {
  const [p, setP] = useState({ theme: "system", digest_window: "72" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api("/api/user/preferences")
      .then((d) => setP({ ...p, ...(d.preferences || {}) }))
      .catch(() => {});
  }, []);

  const save = () => {
    setError("");
    setNotice("");
    api("/api/user/preferences", { method: "POST", body: JSON.stringify(p) })
      .then(() => setNotice("Preferences saved"))
      .catch((e) => setError(e.message));
  };

  return (
    <section>
      <Header eyebrow="Account" title="Preferences" />
      {error && <p className="error">{error}</p>}
      {notice && <p className="muted">{notice}</p>}
      <div className="panel form-grid">
        <Field label="Preferred theme">
          <select value={p.theme} onChange={(e) => setP({ ...p, theme: e.target.value })}>
            <option>system</option>
            <option>dark</option>
            <option>light</option>
          </select>
        </Field>
        <Field label="Digest window hours">
          <input value={p.digest_window} onChange={(e) => setP({ ...p, digest_window: e.target.value })} />
        </Field>
        <Button icon={Settings} onClick={save}>
          Save
        </Button>
      </div>
    </section>
  );
}