import { Component, useEffect, useMemo, useState } from "react";
import { api, clearAuth, getToken } from "./api";
import { Login, PasswordChange } from "./components/Auth";
import { Shell } from "./components/Shell";
import { Dashboard } from "./pages/admin/Dashboard";
import { Testing } from "./pages/admin/Testing";
import { Sources } from "./pages/admin/Sources";
import { Models } from "./pages/admin/Models";
import { UsersPage } from "./pages/admin/Users";
import { Channels } from "./pages/Channels";
import { Mcp } from "./pages/admin/Mcp";
import { Logs } from "./pages/admin/Logs";
import { JsonPage } from "./pages/JsonPage";
import { Feed } from "./pages/user/Feed";
import { Reports } from "./pages/user/Reports";
import { Assistant } from "./pages/user/Assistant";
import { Preferences } from "./pages/user/Preferences";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error.message || String(error) };
  }

  componentDidCatch(error, info) {
    console.error("Runtime error:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, message: "" });
  };

  render() {
    if (this.state.hasError) {
      return (
        <main className="login-screen">
          <div className="login-panel">
            <p className="eyebrow">Unexpected error</p>
            <h1>Something went wrong</h1>
            <p className="muted">{this.state.message}</p>
            <button className="btn" onClick={this.handleReset}>
              Try again
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

function getMode() {
  return location.pathname.startsWith("/admin") ? "admin" : "user";
}

function getDefaultRoute(mode) {
  return mode === "admin" ? "dashboard" : "feed";
}

function getRouteFromHash(mode) {
  const hash = location.hash.slice(1);
  return hash || getDefaultRoute(mode);
}

function App() {
  const [theme, setTheme] = useState(localStorage.getItem("jarvis_theme") || "dark");
  const [user, setUser] = useState(null);
  const [mode, setMode] = useState(() => getMode());
  const [route, setRoute] = useState(() => getRouteFromHash(getMode()));
  const [checking, setChecking] = useState(true);

  // Apply theme
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("jarvis_theme", theme);
  }, [theme]);

  // Listen for hash changes (back/forward buttons, manual hash edits)
  useEffect(() => {
    const onHashChange = () => {
      setRoute(getRouteFromHash(getMode()));
    };
    const onPopState = () => {
      setMode(getMode());
      setRoute(getRouteFromHash(getMode()));
    };
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("popstate", onPopState);
    };
  }, []);

  // Check auth on mount
  useEffect(() => {
    if (getToken()) {
      api("/api/auth/me")
        .then((d) => setUser(d.user))
        .catch(() => {
          clearAuth();
          setUser(null);
        })
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, []);

  const navigate = (id) => {
    if (location.hash.slice(1) === id) return;
    location.hash = id;
    setRoute(id); // Update state immediately for instant UI response
  };

  const switchMode = () => {
    const nextMode = mode === "admin" ? "user" : "admin";
    const nextPath = nextMode === "admin" ? "/admin" : "/user";
    const nextRoute = getDefaultRoute(nextMode);
    // Update URL without full page reload
    window.history.pushState({}, "", nextPath);
    setMode(nextMode);
    setRoute(nextRoute);
  };

  const logout = () => {
    clearAuth();
    setUser(null);
    setRoute(getDefaultRoute(mode));
  };

  const page = useMemo(() => {
    if (mode === "admin") {
      const pages = {
        dashboard: <Dashboard />,
        testing: <Testing />,
        sources: <Sources />,
        models: <Models />,
        users: <UsersPage />,
        integrations: <Channels />,
        mcp: <Mcp />,
        storage: <JsonPage url="/api/admin/system/storage" title="Storage Status" eyebrow="Persistence" />,
        logs: <Logs />,
        health: <JsonPage url="/api/admin/system/health" title="System Health" eyebrow="Runtime" />,
        settings: <JsonPage url="/api/admin/migrations" title="Settings & Migrations" eyebrow="System" />,
      };
      return pages[route] || <Dashboard />;
    }
    const pages = {
      feed: <Feed />,
      reports: <Reports />,
      assistant: <Assistant />,
      notifications: <Channels userMode />,
      preferences: <Preferences />,
    };
    return pages[route] || <Feed />;
  }, [route, mode]);

  if (checking) {
    return (
      <main className="login-screen">
        <div className="login-panel">
          <p className="eyebrow">Secure access</p>
          <h1>JARVIS</h1>
          <p className="muted">Loading...</p>
        </div>
      </main>
    );
  }

  if (!user) return <Login onLogin={setUser} />;
  if (user.must_change_password) return <PasswordChange onChanged={setUser} />;

  return (
    <Shell
      mode={mode}
      theme={theme}
      setTheme={setTheme}
      user={user}
      logout={logout}
      route={route}
      onNavigate={navigate}
      onSwitchMode={switchMode}
    >
      {page}
    </Shell>
  );
}

export default function Root() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}