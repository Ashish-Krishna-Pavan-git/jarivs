import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { api } from "../../api";
import { Button, Header } from "../../components/ui";

export function Assistant() {
  const [query, setQuery] = useState("Explain how to use JARVIS");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = () => {
    setBusy(true);
    setAnswer("Thinking...");
    api("/api/user/assistant", { method: "POST", body: JSON.stringify({ query, hours: 72 }) })
      .then((d) => setAnswer(d.answer))
      .catch((e) => setAnswer(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <section>
      <Header eyebrow="Built-in help" title="JARVIS Assistant" />
      <div className="assistant">
        <textarea value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button icon={MessageSquare} onClick={ask} disabled={busy}>
          {busy ? "Thinking..." : "Ask JARVIS"}
        </Button>
        <pre className="answer">
          {answer || "Ask about setup, errors, reports, integrations, MCP, or recent intelligence."}
        </pre>
      </div>
    </section>
  );
}