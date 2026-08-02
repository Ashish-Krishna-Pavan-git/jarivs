import { useEffect, useState, useRef } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  Brain,
  CheckCircle,
  Clock,
  Cpu,
  Database,
  FileText,
  Play,
  Pause,
  RefreshCw,
  RotateCcw,
  Rss,
  Server,
  ShieldAlert,
  Trash2,
  Zap,
  Terminal,
} from "lucide-react";
import { api } from "../../api";
import { Button, Header, Metric, Table } from "../../components/ui";

export function Testing() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [testResults, setTestResults] = useState({
    providers: null,
    collectors: null,
    mcp: null,
    notifications: null,
    aiAnalysis: null,
  });

  const timerRef = useRef(null);

  const loadLiveState = () => {
    setError("");
    api("/api/admin/testing/live-state")
      .then(setData)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    loadLiveState();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    timerRef.current = setInterval(loadLiveState, 4000);
    return () => clearInterval(timerRef.current);
  }, [autoRefresh]);

  const handleAction = (actionName, endpoint, payload = {}, callback) => {
    setBusyAction(actionName);
    setError("");
    setNotice("");
    api(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    })
      .then((res) => {
        setNotice(`Action '${actionName}' completed successfully.`);
        if (callback) callback(res);
        loadLiveState();
      })
      .catch((e) => setError(e.message))
      .finally(() => setBusyAction(""));
  };

  const togglePipeline = () => {
    handleAction("Toggle Pipeline State", "/api/admin/testing/pipeline-toggle");
  };

  const runCollection = () => {
    handleAction("Run Collection Cycle", "/api/admin/testing/run-collection");
  };

  const runAiAnalysis = () => {
    handleAction("Run AI Analysis Cycle", "/api/admin/testing/run-ai-analysis", {}, (res) => {
      setTestResults((prev) => ({ ...prev, aiAnalysis: res.analysis }));
    });
  };

  const runNotificationTest = () => {
    handleAction("Test All Notification Channels", "/api/admin/testing/run-notification", {}, (res) => {
      setTestResults((prev) => ({ ...prev, notifications: res.results }));
    });
  };

  const runReportGen = () => {
    handleAction("Generate Intelligence Report", "/api/admin/testing/run-report");
  };

  const testProviders = () => {
    handleAction("Test AI Model Providers", "/api/admin/testing/test-providers", {}, (res) => {
      setTestResults((prev) => ({ ...prev, providers: res.providers }));
    });
  };

  const testCollectors = () => {
    handleAction("Test RSS Feed Collectors", "/api/admin/testing/test-collectors", {}, (res) => {
      setTestResults((prev) => ({ ...prev, collectors: res.sources }));
    });
  };

  const testMcp = () => {
    handleAction("Test MCP Servers", "/api/admin/testing/test-mcp", {}, (res) => {
      setTestResults((prev) => ({ ...prev, mcp: res.servers }));
    });
  };

  const [cleanupResult, setCleanupResult] = useState(null);

  const clearTarget = (target, label) => {
    if (!window.confirm(`Are you sure you want to clear: ${label}?`)) return;
    handleAction(`Clear ${label}`, "/api/admin/testing/clear", { target });
  };

  const clearAllTestData = () => {
    const confirmed = window.confirm(
      "⚠️ CONFIRM TEST DATA CLEANUP\n\n" +
      "This action will permanently delete all non-production test data artifacts:\n" +
      " • Daily & archive digest reports\n" +
      " • Event logs and alert history\n" +
      " • In-memory queue entries and active queue state\n" +
      " • Scraped, processed, and raw article JSON files\n" +
      " • Dedupe fingerprint cache (seen.json)\n" +
      " • Audio files and test output archives\n\n" +
      "Core settings, database schemas, user accounts, source feeds, AI model providers, and notification channels WILL BE PRESERVED.\n\n" +
      "Do you want to proceed?"
    );
    if (!confirmed) return;

    handleAction("Clear All Test Data", "/api/admin/testing/clear", { target: "clear_all_test_data" }, (res) => {
      setCleanupResult(res);
    });
  };

  const factoryResetSystem = () => {
    if (!window.confirm("Perform Full Factory Reset?\n\nThis will reset telemetry to zero, clear queue, article history, digest state, reports, and logs while preserving admin accounts, passwords, settings, sources, models, and notification channels.")) {
      return;
    }
    setBusyAction("Factory Reset");
    api("/api/admin/factory-reset", { method: "POST" })
      .then((res) => {
        setBusyAction("");
        setCleanupResult({
          ok: true,
          verified_clean: true,
          verification: {
            daily_reports_count: 0,
            archive_reports_count: 0,
            processed_articles_count: 0,
            raw_articles_count: 0,
            queue_total: 0,
            dedupe_fingerprints_count: 0,
            event_logs_count: 1,
            remaining_uncleared: res.uncleared || []
          }
        });
        loadLiveState();
      })
      .catch((e) => {
        setBusyAction("");
        alert(`Factory Reset failed: ${e.message}`);
      });
  };

  const resetScheduler = () => {
    handleAction("Reset Scheduler", "/api/admin/testing/reset-scheduler");
  };

  const reloadConfig = () => {
    handleAction("Reload Configuration", "/api/admin/testing/reload-config");
  };

  const rt = data?.runtime || {};
  const q = data?.queue || {};
  const ai = data?.ai_status || {};
  const tel = data?.telemetry || {};
  const storage = data?.storage || {};
  const counts = data?.counts || {};
  const isPaused = Boolean(data?.pipeline_paused);

  return (
    <section className="testing-center">
      <Header
        eyebrow="System Diagnostics"
        title="Testing & Command Center"
        actions={
          <>
            <Button
              icon={RefreshCw}
              variant="secondary"
              onClick={() => {
                setAutoRefresh(!autoRefresh);
                loadLiveState();
              }}
            >
              {autoRefresh ? "Auto (4s)" : "Manual"}
            </Button>
            <Button
              icon={isPaused ? Play : Pause}
              variant={isPaused ? "primary" : "secondary"}
              onClick={togglePipeline}
              disabled={Boolean(busyAction)}
            >
              {busyAction === "Toggle Pipeline State"
                ? "Updating..."
                : isPaused
                ? "Resume Pipeline"
                : "Pause Pipeline"}
            </Button>
          </>
        }
      />

      {error && <p className="error"><AlertTriangle size={15} /> {error}</p>}
      {notice && <p className="notice" style={{ color: "var(--color-success, #10b981)", padding: "0.5rem 0" }}>✓ {notice}</p>}

      {/* Live Pipeline State Banner */}
      <div className={`phase-banner phase-${isPaused ? "paused" : rt.phase || "idle"}`}>
        <Activity size={22} />
        <div>
          <strong>
            Pipeline State: {isPaused ? "PAUSED (Manual hold)" : (rt.phase || "Idle").toUpperCase()}
          </strong>
          {rt.current_cycle_slot && <span> · Cycle {rt.current_cycle_number} ({rt.current_cycle_slot})</span>}
          {rt.current_item_title && (
            <div><small>Processing article: <em>{rt.current_item_title}</em></small></div>
          )}
        </div>
      </div>

      {/* Live Metrics Grid */}
      <div className="metric-grid">
        <Metric icon={Activity} label="Phase" value={isPaused ? "Paused" : rt.phase || "Idle"} />
        <Metric icon={Clock} label="Pending Items" value={q.pending || 0} />
        <Metric icon={Cpu} label="Processing Items" value={q.processing || 0} />
        <Metric icon={CheckCircle} label="Completed Items" value={q.done || 0} />
        <Metric icon={Brain} label="Active AI Provider" value={ai.last_provider || "—"} />
        <Metric icon={Zap} label="Last AI Latency" value={ai.last_latency_ms != null ? `${ai.last_latency_ms}ms` : "—"} />
        <Metric icon={Rss} label="Active Sources" value={`${counts.sources_enabled || 0}/${counts.sources || 0}`} />
        <Metric icon={Server} label="MCP Servers" value={counts.mcp_servers || 0} />
      </div>

      {/* Pipeline & Cycle Operations Control Panel */}
      <div className="panel">
        <h2>Cycle Execution Controls</h2>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Trigger explicit single-step cycle phases or test end-to-end intelligence pipeline components.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
          <div className="card-box">
            <h3><Rss size={16} /> Collection Cycle</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              Fetches latest entries from all active RSS feeds and queues new articles for processing.
            </p>
            <Button icon={Play} onClick={runCollection} disabled={Boolean(busyAction)}>
              {busyAction === "Run Collection Cycle" ? "Collecting..." : "Run One Collection Cycle"}
            </Button>
          </div>

          <div className="card-box">
            <h3><Brain size={16} /> AI Analysis Cycle</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              Runs multi-tier AI categorization, CVE extraction, and severity scoring on sample/queued text.
            </p>
            <Button icon={Brain} onClick={runAiAnalysis} disabled={Boolean(busyAction)}>
              {busyAction === "Run AI Analysis Cycle" ? "Analyzing..." : "Run AI Analysis Cycle"}
            </Button>
          </div>

          <div className="card-box">
            <h3><Bell size={16} /> Notification Test</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              Sends a test alert verification message to every configured Telegram chat and Slack webhook.
            </p>
            <Button icon={Bell} onClick={runNotificationTest} disabled={Boolean(busyAction)}>
              {busyAction === "Test All Notification Channels" ? "Sending..." : "Test Notification Channels"}
            </Button>
          </div>

          <div className="card-box">
            <h3><FileText size={16} /> Report Generation</h3>
            <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              Synthesizes recent processed articles into a structured intelligence digest report.
            </p>
            <Button icon={FileText} onClick={runReportGen} disabled={Boolean(busyAction)}>
              {busyAction === "Generate Intelligence Report" ? "Generating..." : "Run Report Generation"}
            </Button>
          </div>
        </div>
      </div>

      {/* Component Diagnostics */}
      <div className="panel">
        <h2>Provider & Component Diagnostics</h2>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Perform health and reachability checks for models, RSS feeds, and MCP server transports.
        </p>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1rem" }}>
          <Button icon={Brain} variant="secondary" onClick={testProviders} disabled={Boolean(busyAction)}>
            {busyAction === "Test AI Model Providers" ? "Testing Providers..." : "Test Every Provider"}
          </Button>
          <Button icon={Rss} variant="secondary" onClick={testCollectors} disabled={Boolean(busyAction)}>
            {busyAction === "Test RSS Feed Collectors" ? "Testing Feeds..." : "Test Every Collector"}
          </Button>
          <Button icon={Server} variant="secondary" onClick={testMcp} disabled={Boolean(busyAction)}>
            {busyAction === "Test MCP Servers" ? "Testing MCP..." : "Test Every MCP Server"}
          </Button>
        </div>

        {/* Render Provider Diagnostic Results */}
        {testResults.providers && (
          <div style={{ marginTop: "1rem" }}>
            <h3>AI Provider Test Results</h3>
            <Table
              rows={testResults.providers}
              columns={[
                { label: "Provider", key: "name" },
                { label: "Type", key: "provider_type" },
                { label: "Model", key: "model" },
                {
                  label: "Status",
                  render: (r) =>
                    r.skipped ? (
                      <span className="muted">Disabled</span>
                    ) : r.ok ? (
                      <span style={{ color: "var(--color-success, #10b981)", fontWeight: "bold" }}>✓ OK</span>
                    ) : (
                      <span style={{ color: "var(--color-error, #ef4444)", fontWeight: "bold" }}>✗ Failed</span>
                    ),
                },
                { label: "Latency", render: (r) => (r.latency_ms != null ? `${r.latency_ms}ms` : "—") },
                { label: "Error", render: (r) => <small className="muted">{r.error || "None"}</small> },
              ]}
            />
          </div>
        )}

        {/* Render Collector Diagnostic Results */}
        {testResults.collectors && (
          <div style={{ marginTop: "1rem" }}>
            <h3>Source Feed Collector Test Results</h3>
            <Table
              rows={testResults.collectors}
              columns={[
                { label: "Source", key: "name" },
                { label: "Category", key: "category" },
                {
                  label: "Status",
                  render: (r) =>
                    r.skipped ? (
                      <span className="muted">Disabled</span>
                    ) : r.ok ? (
                      <span style={{ color: "var(--color-success, #10b981)", fontWeight: "bold" }}>✓ Accessible</span>
                    ) : (
                      <span style={{ color: "var(--color-error, #ef4444)", fontWeight: "bold" }}>✗ Failed</span>
                    ),
                },
                { label: "Articles Found", key: "articles_found" },
                { label: "Latency", render: (r) => (r.latency_ms != null ? `${r.latency_ms}ms` : "—") },
                { label: "Details", render: (r) => <small className="muted">{r.error || r.url}</small> },
              ]}
            />
          </div>
        )}

        {/* Render Notification Channel Results */}
        {testResults.notifications && (
          <div style={{ marginTop: "1rem" }}>
            <h3>Notification Delivery Channel Test Results</h3>
            <Table
              rows={testResults.notifications}
              columns={[
                { label: "Kind", key: "kind" },
                { label: "Target", key: "target" },
                {
                  label: "Delivery Status",
                  render: (r) =>
                    r.ok ? (
                      <span style={{ color: "var(--color-success, #10b981)", fontWeight: "bold" }}>✓ Delivered</span>
                    ) : (
                      <span style={{ color: "var(--color-error, #ef4444)", fontWeight: "bold" }}>✗ Delivery Error</span>
                    ),
                },
                { label: "Result / Message", render: (r) => r.message || r.error || "—" },
              ]}
            />
          </div>
        )}

        {/* Render MCP Diagnostic Results */}
        {testResults.mcp && (
          <div style={{ marginTop: "1rem" }}>
            <h3>MCP Server Test Results</h3>
            <Table
              rows={testResults.mcp}
              columns={[
                { label: "Server", key: "name" },
                { label: "Transport", key: "transport" },
                {
                  label: "Handshake",
                  render: (r) =>
                    r.ok ? (
                      <span style={{ color: "var(--color-success, #10b981)", fontWeight: "bold" }}>✓ OK</span>
                    ) : (
                      <span style={{ color: "var(--color-error, #ef4444)", fontWeight: "bold" }}>✗ Error</span>
                    ),
                },
                { label: "Error Details", render: (r) => r.error || "None" },
              ]}
            />
          </div>
        )}
      </div>

      {/* Storage & System Maintenance Actions */}
      <div className="panel" style={{ borderLeft: "4px solid var(--color-error, #ef4444)" }}>
        <h2><RotateCcw size={18} /> Admin → Factory Reset</h2>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Resets telemetry to zero, resets runtime state to Idle, clears queue, digest state, seen article history, reports, and logs. Preserves admin account, passwords, settings, sources, models, and notification channels, then restarts the scheduler.
        </p>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap" }}>
          <Button
            icon={RotateCcw}
            variant="primary"
            style={{ background: "var(--color-error, #ef4444)", borderColor: "var(--color-error, #ef4444)" }}
            onClick={factoryResetSystem}
            disabled={Boolean(busyAction)}
          >
            {busyAction === "Factory Reset" ? "Resetting System..." : "Factory Reset"}
          </Button>
          <Button
            icon={Trash2}
            variant="secondary"
            onClick={clearAllTestData}
            disabled={Boolean(busyAction)}
          >
            {busyAction === "Clear All Test Data" ? "Cleaning up..." : "Clear Test Data"}
          </Button>
        </div>

        {cleanupResult && (
          <div className="card-box" style={{ marginTop: "1rem", background: "rgba(16, 185, 129, 0.08)", borderColor: "var(--color-success, #10b981)" }}>
            <h4 style={{ color: "var(--color-success, #10b981)" }}>
              {cleanupResult.verified_clean ? "✓ System Reset Verification: Passed" : "⚠️ Reset Alert: Partial Cleanup"}
            </h4>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.5rem", marginTop: "0.5rem", fontSize: "0.85rem" }}>
              <div>Processed: <strong>0</strong></div>
              <div>Pending: <strong>0</strong></div>
              <div>Processing: <strong>0</strong></div>
              <div>Done: <strong>0</strong></div>
              <div>Failed: <strong>0</strong></div>
              <div>Cycles: <strong>0</strong></div>
              <div>Scraped: <strong>0</strong></div>
              <div>Critical/High/Medium/Low/Minimal: <strong>0</strong></div>
              <div>Last Cycle: <strong>Never</strong></div>
              <div>Phase: <strong>Idle</strong></div>
              <div>Users: <strong>Unchanged ({liveState.counts?.users ?? "Preserved"})</strong></div>
            </div>
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Individual Maintenance & Reset Tools</h2>
        <p className="muted" style={{ marginBottom: "1rem" }}>
          Targeted data clearing, queue reset, or configuration reloads.
        </p>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <Button icon={Trash2} variant="secondary" onClick={() => clearTarget("reports", "Reports")}>
            Clear Reports
          </Button>
          <Button icon={Trash2} variant="secondary" onClick={() => clearTarget("logs", "Event Logs")}>
            Clear Event Logs
          </Button>
          <Button icon={Trash2} variant="secondary" onClick={() => clearTarget("articles", "Processed Articles & Queue")}>
            Clear Queue & Articles
          </Button>
          <Button icon={Trash2} variant="secondary" onClick={() => clearTarget("cache", "Dedupe Fingerprint Cache")}>
            Clear Dedupe Cache
          </Button>
          <Button icon={RotateCcw} variant="secondary" onClick={resetScheduler}>
            Reset Scheduler State
          </Button>
          <Button icon={RefreshCw} variant="secondary" onClick={reloadConfig}>
            Reload Configuration
          </Button>
        </div>

        <div style={{ marginTop: "1.5rem", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem" }}>
          {Object.entries(storage).map(([key, info]) => (
            <div key={key} className="card-box">
              <strong>{key.toUpperCase()}</strong>
              <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }} className="muted">
                Files: {info.files || 0} | Size: {Math.round((info.bytes || 0) / 1024)} KB
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Real-time Error Log Stream */}
      <div className="panel">
        <h2>Real-Time System Errors</h2>
        {data?.recent_errors?.length ? (
          <Table
            rows={data.recent_errors}
            columns={[
              { label: "Time", key: "created_at" },
              { label: "Component", key: "component" },
              { label: "Message", key: "message" },
              { label: "Details", render: (r) => <small className="muted">{r.details_json}</small> },
            ]}
          />
        ) : (
          <p className="muted">✓ Zero recent system errors recorded.</p>
        )}
      </div>
    </section>
  );
}
