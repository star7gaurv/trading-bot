/**
 * API client for the FinBuddy dashboard.
 *
 * - All requests go through `request()` which attaches the Bearer token
 *   from localStorage.
 * - 401 responses clear the token and trigger a reload (which re-shows LoginGate).
 * - 5xx and network errors throw with a useful message.
 */

const TOKEN_KEY = "finbuddy_dashboard_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || null;
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function baseUrl() {
  // Same origin — nginx proxies /api/* to the streamer
  return `${window.location.protocol}//${window.location.host}`;
}

async function request(path, { method = "GET", body, signal } = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${baseUrl()}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (res.status === 401) {
    clearToken();
    // Soft reload — App will route back to LoginGate
    window.dispatchEvent(new CustomEvent("finbuddy:auth:expired"));
    throw new Error("Session expired — please log in again");
  }

  let data = null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    data = await res.json();
  }

  if (!res.ok) {
    const msg = (data && (data.error || data.detail)) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

// ─── Auth ───
export async function login(password) {
  const data = await request("/api/auth/login", { method: "POST", body: { password } });
  if (data?.token) setToken(data.token);
  return data;
}

export async function whoami() {
  return request("/api/auth/me");
}

export async function logout() {
  clearToken();
}

// ─── System ───
export async function getCronStatus() {
  return request("/api/cron/status");
}
export async function getSystemHealth() {
  return request("/api/system/health");
}

// ─── Brain & WF ───
export async function getBrainQueue() {
  return request("/api/brain/queue");
}
export async function getBrainExperiments(limit = 50) {
  return request(`/api/brain/experiments?limit=${limit}`);
}
export async function getWfLatest() {
  return request("/api/wf/latest");
}
export async function getWfHistory(limit = 20) {
  return request(`/api/wf/history?limit=${limit}`);
}

export async function getRunningFolds() {
  return request("/api/wf/running-folds");
}

// ─── Regime ───
export async function getRegimeCurrent() {
  return request("/api/regime/current");
}
export async function getRegimePairStats() {
  return request("/api/regime/pair-stats");
}

// ─── Trades ───
export async function getOpenTrades() {
  return request("/api/trades/open");
}
export async function getClosedTrades({ limit = 50, offset = 0 } = {}) {
  return request(`/api/trades/closed?limit=${limit}&offset=${offset}`);
}

// ─── Performance ───
export async function getDailyPerformance(days = 30) {
  return request(`/api/performance/daily?days=${days}`);
}
export async function getWeeklyPerformance(weeks = 12) {
  return request(`/api/performance/weekly?weeks=${weeks}`);
}
export async function getMonthlyPerformance(months = 6) {
  return request(`/api/performance/monthly?months=${months}`);
}
export async function getPairPerformance() {
  return request("/api/performance/pair");
}
export async function getProfitSummary() {
  return request("/api/profit");
}
export async function getBalance() {
  return request("/api/balance");
}
export async function getWhitelist() {
  return request("/api/whitelist");
}
export async function getStrategyConfig() {
  return request("/api/config");
}

// ─── Stats & diagnostics ───
export async function getExitReasons() {
  return request("/api/stats/exit-reasons");
}
export async function getRecentTrades(limit = 10) {
  return request(`/api/trades/recent?limit=${limit}`);
}

// ─── WebSockets — same-origin, nginx already proxies /ws/ ───
// Token must be passed as ?token= query param — WebSocket API has no
// custom header support, so Bearer in Authorization is not possible.
export function brainLogSocket() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const token = encodeURIComponent(getToken() || "");
  return new WebSocket(`${proto}//${window.location.host}/ws/brain?token=${token}`);
}
export function memorySocket() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const token = encodeURIComponent(getToken() || "");
  return new WebSocket(`${proto}//${window.location.host}/ws/memory?token=${token}`);
}
