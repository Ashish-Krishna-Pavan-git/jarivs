import { useEffect, useState } from "react";
import { Bell, RefreshCw, Slack, Send, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { api } from "../api";
import { Button, Field, Header, Table } from "../components/ui";

export function Channels({ userMode = false }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [testResults, setTestResults] = useState({});
  const [f, setF] = useState({ kind: "telegram", label: "", target: "", enabled: true });
  const base = userMode ? "/api/user/notification-channels" : "/api/admin/notification-channels";
  const testUrl = userMode ? "/api/user/notification-channels/test" : "/api/admin/notification-channels/test";

  const load = () => {
    setError("");
    setLoading(true);
    api(base)
      .then((d) => {
        setRows(d.channels || []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  };

  useEffect(load, [base]);

  const save = () => {
    setError("");
    api(base, {
      method: "POST",
      body: JSON.stringify({
        ...f,
        secret: f.kind === "slack" ? { webhook_url: f.target } : { chat_id: f.target },
      }),
    })
      .then(() => {
        setF({ kind: "telegram", label: "", target: "", enabled: true });
        load();
      })
      .catch((e) => setError(e.message));
  };

  const disable = (id) => {
    setError("");
    api(`${base}/${id}`, { method: "DELETE" })
      .then(load)
      .catch((e) => setError(e.message));
  };

  const testChannel = (channel) => {
    setTestResults({ ...testResults, [channel.id]: { loading: true } });
    api(testUrl, {
      method: "POST",
      body: JSON.stringify({
        kind: channel.kind,
        target: channel.target,
        secret: channel.secret || (channel.kind === "slack" ? { webhook_url: channel.target } : {}),
      }),
    })
      .then((res) => {
        setTestResults({ ...testResults, [channel.id]: res });
      })
      .catch((e) => {
        setTestResults({ ...testResults, [channel.id]: { ok: false, error: e.message } });
      });
  };

  const testNew = () => {
    if (!f.target) {
      setError("Enter a target before testing");
      return;
    }
    setTestResults({ ...testResults, _new: { loading: true } });
    api(testUrl, {
      method: "POST",
      body: JSON.stringify({
        kind: f.kind,
        target: f.target,
        secret: f.kind === "slack" ? { webhook_url: f.target } : {},
      }),
    })
      .then((res) => setTestResults({ ...testResults, _new: res }))
      .catch((e) => setTestResults({ ...testResults, _new: { ok: false, error: e.message } }));
  };

  const renderTestResult = (id) => {
    const r = testResults[id];
    if (!r) return null;
    if (r.loading) return <span className="test-pending"><Loader2 size={14} className="spin" /> Testing...</span>;
    if (r.ok) return <span className="test-ok"><CheckCircle size={14} /> {r.message || "Sent"}</span>;
    return <span className="test-fail"><XCircle size={14} /> {r.error || "Failed"}</span>;
  };

  return (
    <section>
      <Header
        eyebrow="Delivery"
        title={userMode ? "Notifications" : "Telegram / Slack Integrations"}
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      <div className="panel guide-grid">
        <div>
          <h2>Setup Guide</h2>
          <p>
            <strong>Telegram:</strong> Enter your chat ID (numeric). Message @userinfobot to get yours,
            or start your bot with /start. <strong>Slack:</strong> Paste an incoming webhook URL from
            your Slack app settings. Use the Test button to verify delivery.
          </p>
        </div>
        <div className="form-grid">
          <Field label="Kind">
            <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option>telegram</option>
              <option>slack</option>
            </select>
          </Field>
          <Field label="Label">
            <input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
          </Field>
          <Field label={f.kind === "slack" ? "Webhook URL" : "Chat ID"}>
            <input value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} />
          </Field>
          <label className="check">
            <input
              type="checkbox"
              checked={f.enabled}
              onChange={(e) => setF({ ...f, enabled: e.target.checked })}
            />{" "}
            Enabled
          </label>
          <Button icon={Send} variant="secondary" onClick={testNew}>
            Test
          </Button>
          <Button icon={f.kind === "slack" ? Slack : Bell} onClick={save}>
            Save Channel
          </Button>
          {renderTestResult("_new")}
        </div>
      </div>
      {loading ? (
        <p className="muted">Loading channels...</p>
      ) : (
        <Table
          rows={rows}
          columns={[
            { label: "Kind", key: "kind" },
            { label: "Label", key: "label" },
            { label: "Target", key: "target" },
            { label: "Enabled", render: (r) => (r.enabled ? "Yes" : "No") },
            {
              label: "Test",
              render: (r) => (
                <div className="test-cell">
                  <Button variant="secondary" onClick={() => testChannel(r)}>
                    <Send size={12} /> Test
                  </Button>
                  {renderTestResult(r.id)}
                </div>
              ),
            },
            {
              label: "Action",
              render: (r) => (
                <Button variant="danger" onClick={() => disable(r.id)}>
                  Disable
                </Button>
              ),
            },
          ]}
          empty="No notification channels configured"
        />
      )}
    </section>
  );
}