import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "../api";
import { Button, Header } from "../components/ui";

export function JsonPage({ url, title, eyebrow }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    api(url)
      .then(setD)
      .catch((e) => setError(e.message));
  };

  useEffect(load, [url]);

  return (
    <section>
      <Header
        eyebrow={eyebrow}
        title={title}
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      <pre className="code-panel">{JSON.stringify(d || {}, null, 2)}</pre>
    </section>
  );
}