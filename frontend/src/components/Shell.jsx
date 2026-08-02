import { Bell, Bot, Brain, Database, FileText, HeartPulse, Home, Link2, LogOut, Moon, Rss, Settings, Sun, Terminal, Users } from "lucide-react";

const adminNav = [
  ["dashboard", Home, "Dashboard"],
  ["testing", Terminal, "Testing Center"],
  ["sources", Rss, "Sources"],
  ["models", Brain, "Models"],
  ["users", Users, "Users"],
  ["integrations", Bell, "Integrations"],
  ["mcp", Link2, "MCP"],
  ["storage", Database, "Storage"],
  ["logs", FileText, "Logs"],
  ["health", HeartPulse, "Health"],
  ["settings", Settings, "Settings"],
];

const userNav = [
  ["feed", Home, "Feed"],
  ["reports", FileText, "Reports"],
  ["assistant", Bot, "Assistant"],
  ["notifications", Bell, "Notifications"],
  ["preferences", Settings, "Preferences"],
];

export function Shell({ mode, theme, setTheme, user, logout, route, onNavigate, onSwitchMode, children }) {
  const nav = mode === "admin" ? adminNav : userNav;
  const defaultRoute = mode === "admin" ? "dashboard" : "feed";
  const active = route || defaultRoute;

  return (
    <main className="app-shell">
      <aside className="side">
        <div className="brand">
          <span>J</span>
          <div>
            <strong>JARVIS</strong>
            <small>{mode === "admin" ? "Admin Control" : "Intelligence Console"}</small>
          </div>
        </div>
        <nav className="nav">
          {nav.map(([id, Icon, label]) => (
            <button
              key={id}
              className={active === id ? "active" : ""}
              onClick={() => onNavigate(id)}
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            {theme === "dark" ? "Light" : "Dark"}
          </button>
          <button onClick={onSwitchMode}>
            {mode === "admin" ? "User Console" : "Admin"}
          </button>
          <button onClick={logout}>
            <LogOut size={16} /> Logout
          </button>
          <small>{user.username}</small>
        </div>
      </aside>
      <section className="main">{children}</section>
    </main>
  );
}