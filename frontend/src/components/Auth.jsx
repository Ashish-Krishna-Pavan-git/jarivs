import { useState } from "react";
import { KeyRound, Shield } from "lucide-react";
import { api, setAuth } from "../api";
import { Button, Field } from "./ui";

export function Login({ onLogin }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const d = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setAuth(d.token, d.csrf);
      onLogin(d.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <form className="login-panel" onSubmit={submit}>
        <p className="eyebrow">Secure access</p>
        <h1>JARVIS Login</h1>
        <p className="muted">
          Fresh Docker installs use <code>admin</code> / <code>admin123!ChangeMe</code> and then
          require a new password.
        </p>
        <Field label="Username">
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </Field>
        <Field label="Password">
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
        </Field>
        <Button icon={KeyRound} disabled={busy}>
          {busy ? "Signing in..." : "Login"}
        </Button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  );
}

export function PasswordChange({ onChanged }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const d = await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      setAuth(d.token, d.csrf);
      onChanged(d.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <form className="login-panel" onSubmit={submit}>
        <p className="eyebrow">First login</p>
        <h1>Change Password</h1>
        <Field label="Current password">
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password">
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <Button icon={Shield} disabled={busy}>
          {busy ? "Saving..." : "Save Password"}
        </Button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  );
}