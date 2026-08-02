import { useEffect, useState } from "react";
import { RefreshCw, Search, ChevronDown, ChevronUp, Rss } from "lucide-react";
import { api } from "../../api";
import { Button, Header } from "../../components/ui";

const SEV_COLORS = {
  CRITICAL: "sev-critical",
  HIGH: "sev-high",
  MEDIUM: "sev-medium",
  LOW: "sev-low",
  MINIMAL: "sev-minimal",
};

export function Feed() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(72);
  const [q, setQ] = useState("");
  const [severity, setSeverity] = useState("");
  const [expanded, setExpanded] = useState(null);

  const load = () => {
    setError("");
    setLoading(true);
    api(`/api/user/feed?hours=${hours}&q=${encodeURIComponent(q)}&severity=${severity}`)
      .then((d) => {
        setRows(d.items || []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  };

  useEffect(load, []);

  const toggle = (i) => setExpanded(expanded === i ? null : i);

  const renderSummary = (item) => {
    const summary = item.summary || [];
    const summaryList = Array.isArray(summary) ? summary : [summary];
    return (
      <div className="feed-detail">
        {summaryList.length > 0 && (
          <div className="detail-section">
            <h4>📋 Analysis</h4>
            {summaryList.map((s, j) => (
              <p key={j}>• {s}</p>
            ))}
          </div>
        )}
        {item.cves?.length > 0 && (
          <div className="detail-section">
            <h4>🔴 CVEs</h4>
            <p>{item.cves.join(", ")}</p>
          </div>
        )}
        {item.actors?.length > 0 && (
          <div className="detail-section">
            <h4>🎭 Actors</h4>
            <p>{item.actors.join(", ")}</p>
          </div>
        )}
        {item.affected_products?.length > 0 && (
          <div className="detail-section">
            <h4>📦 Affected Products</h4>
            <p>{item.affected_products.join(", ")}</p>
          </div>
        )}
        {item.tags?.length > 0 && (
          <div className="detail-section">
            <h4>🏷️ Tags</h4>
            <p>{item.tags.join(", ")}</p>
          </div>
        )}
        <div className="detail-meta">
          <span>Scraped: {item.scraped ? "Yes" : "RSS only"}</span>
          {item.paywall && <span> · Paywall</span>}
        </div>
      </div>
    );
  };

  return (
    <section>
      <Header
        eyebrow="Intelligence"
        title="Feed"
        actions={
          <Button icon={RefreshCw} variant="secondary" onClick={load}>
            Refresh
          </Button>
        }
      />
      {error && <p className="error">{error}</p>}
      <div className="toolbar">
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          <option value={24}>24h</option>
          <option value={72}>72h</option>
          <option value={168}>7d</option>
        </select>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <input placeholder="Search intelligence" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button icon={Search} onClick={load}>
          Search
        </Button>
      </div>
      {loading ? (
        <p className="muted">Loading feed...</p>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <Rss size={48} />
          <h3>No intelligence items</h3>
          <p className="muted">
            No articles found for the selected time range. Run a collection cycle from the Admin
            Dashboard to populate the feed.
          </p>
        </div>
      ) : (
        <div className="feed-list">
          {rows.map((r, i) => (
            <article className={`feed-item ${SEV_COLORS[r.severity] || ""}`} key={i}>
              <div className="feed-item-header" onClick={() => toggle(i)}>
                <div className="feed-item-main">
                  <span className={`sev-badge sev-${(r.severity || "low").toLowerCase()}`}>
                    {r.severity || "LOW"}
                  </span>
                  <span className="feed-category">{r.category || "tech"}</span>
                  {r.confidence != null && (
                    <span className="feed-confidence">conf: {r.confidence}/10</span>
                  )}
                  <a href={r.link} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    {r.title}
                  </a>
                </div>
                <div className="feed-item-meta">
                  <span className="muted">{r.source}</span>
                  <span className="muted">{r.saved_at ? new Date(r.saved_at).toLocaleString() : ""}</span>
                  <button className="expand-btn">
                    {expanded === i ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>
              </div>
              {expanded === i && renderSummary(r)}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}