// Centralized API helper with robust error handling.
const store = {
  token: localStorage.getItem("jarvis_token") || "",
  csrf: localStorage.getItem("jarvis_csrf") || "",
};

export function setAuth(token, csrf) {
  store.token = token || "";
  store.csrf = csrf || "";
  if (token) localStorage.setItem("jarvis_token", token);
  else localStorage.removeItem("jarvis_token");
  if (csrf) localStorage.setItem("jarvis_csrf", csrf);
  else localStorage.removeItem("jarvis_csrf");
}

export function clearAuth() {
  store.token = "";
  store.csrf = "";
  localStorage.removeItem("jarvis_token");
  localStorage.removeItem("jarvis_csrf");
}

export function getToken() {
  return store.token;
}

function buildHeaders(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  if (store.token) h["Authorization"] = `Bearer ${store.token}`;
  if (store.csrf) h["X-CSRF-Token"] = store.csrf;
  return h;
}

export async function api(url, options = {}) {
  const hasBody = options.body !== undefined;
  const res = await fetch(url, {
    credentials: "include",
    ...options,
    headers: { ...buildHeaders(hasBody), ...(options.headers || {}) },
  });
  const text = await res.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      // Non-JSON response (e.g. HTML error page) — keep data as {}.
      data = { error: text.slice(0, 200) };
    }
  }
  if (!res.ok) {
    const err = new Error(data.error || text || res.statusText || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}