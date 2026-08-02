import { useEffect, useState } from "react";
import { RefreshCw, FileText, ChevronDown, ChevronUp, AlertCircle, Download } from "lucide-react";
import { api } from "../../api";
import { Button, Header } from "../../components/ui";

export function Reports() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [days, setDays] = useState(30);

  const load = () => {
    setError("");
    setLoading(true);
    api(`/api/user/reports?days=${days}`)
      .then((d) => {
        setRows(d.reports || []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  };

  useEffect(load, [days]);

  const toggle = (i) => setExpanded(expanded === i ? null : i);

  const downloadReport = (r, format) => {
    const reportId = r.id || r.generated_at || r.report_date || r._legacy_path || r._runtime_path || "digest";
    window.open(`/api/user/reports/${encodeURIComponent(reportId)}/export?format=${format}`, "_blank");
  };

  const renderReportBody = (r) => {
    const sections = [];
    if (r.cybersec_updates?.length) sections.push(["🛡️ Cybersecurity", r.cybersec_updates]);
    if (r.ai_updates?.length) sections.push(["🧠 AI", r.ai_updates]);
    if (r.tech_business_updates?.length) sections.push(["💼 Tech & Business", r.tech_business_updates]);
    if (r.hardware_mobile_updates?.length) sections.push(["📱 Hardware & Mobile", r.hardware_mobile_updates]);
    if (r.escalating_threats?.length) sections.push(["🔺 Escalating Threats", r.escalating_threats]);
    if (r.new_patterns?.length) sections.push(["🔍 Patterns", r.new_patterns]);
    if (r.actor_activity?.length) sections.push(["🎭 Actor Activity", r.actor_activity]);
    if (r.tech_trends?.length) sections.push(["💡 Tech Trends", r.tech_trends]);
    if (r.recommendations?.length) sections.push(["✅ Recommendations", r.recommendations]);
    if (r.doom?.length) sections.push(["🌋 Doom", r.doom]);
    if (r.bloom?.length) sections.push(["🌸 Bloom", r.bloom]);
    if (r.key_cves?.length) sections.push(["🔴 CVEs", r.key_cves]);

    return (
      <div className="report-body">
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          <Button icon={Download} variant="secondary" onClick={() => downloadReport(r, "markdown")}>
            Export Markdown
          </Button>
          <Button icon={Download} variant="secondary" onClick={() => downloadReport(r, "json")}>
            Export JSON
          </Button>
        </div>
        {r.day_summary && <p className="report-summary">{r.day_summary}</p>}
        {r.risk_level && <p className="risk-level">Risk Level: <strong>{r.risk_level}</strong></p>}
        {sections.map(([title, items]) => (
          <div key={title} className="report-section">
            <h4>{title}</h4>
            {items.map((item, j) => (
              <p key={j}>{typeof item === "string" ? item : JSON.stringify(item)}</p>
            ))}
          </div>
        ))}
        {r._degraded && (
          <p className="warn">
            <AlertCircle size={14} /> AI synthesis was unavailable — showing degraded mode report.
          </p>
        )}
      </div>
    );
  };

  return (
    <section>
      <Header
        eyebrow="Digest archive"
        title="Reports"
        actions={
          <>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
            </select>
            <Button icon={RefreshCw} variant="secondary" onClick={load}>
              Refresh
            </Button>
          </>
        }
      />
      {error && <p className="error">{error}</p>}
      {loading ? (
        <p className="muted">Loading reports...</p>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <FileText size={48} />
          <h3>No reports yet</h3>
          <p className="muted">
            Reports are generated after each collection cycle. Run a cycle from the Admin Dashboard
            to generate intelligence digests.
          </p>
        </div>
      ) : (
        <div className="report-list">
          {rows.map((r, i) => (
            <article className="report" key={i}>
              <div className="report-header" onClick={() => toggle(i)}>
                <div>
                  <p className="eyebrow">
                    {r.report_date || r._legacy_path || r._runtime_path || "report"}
                    {r._degraded && " · degraded"}
                  </p>
                  <h3>{r.headline || r.day_headline || "Digest"}</h3>
                </div>
                <button className="expand-btn">
                  {expanded === i ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </button>
              </div>
              <p className="report-snippet">
                {r.strategic_note || r.day_summary || "Saved report"}
              </p>
              {expanded === i && renderReportBody(r)}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}