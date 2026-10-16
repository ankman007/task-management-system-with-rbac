// Thin wrapper around fetch() for the Task Management API.
//
// API_BASE is empty because the frontend is served by nginx on the same origin,
// which proxies /auth, /tasks, /users and /roles to the FastAPI container.
// (The API has no CORS headers, so calling http://localhost:18000 directly from
// a page on another origin is blocked by the browser.)
const API_BASE = "";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// FastAPI returns { detail: "..." } for HTTP errors and
// { detail: [{ msg, loc }, ...] } for validation errors (422).
function errorMessage(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join(" ");
  }
  return `Request failed (${status}).`;
}

function queryString(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") qs.set(key, value);
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

// Several requests can hit a 401 at once; they all wait on the same refresh.
let refreshInFlight = null;

function refreshSession() {
  const session = getSession();
  if (!session || !session.refresh_token) return Promise.resolve(false);

  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refresh_token }),
    })
      .then(async (res) => {
        if (!res.ok) return false;
        const tokens = await res.json();
        // /auth/refresh returns tokens only, so keep the stored user profile.
        saveSession({ ...tokens, user: session.user });
        return true;
      })
      .catch(() => false)
      .finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

async function apiRequest(path, { method = "GET", body, auth = true, retry = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const session = getSession();
    if (session) headers.Authorization = `Bearer ${session.access_token}`;
  }

  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach the API. Is the backend running?", 0);
  }

  // Access token expired: refresh once and replay the request.
  if (res.status === 401 && auth) {
    if (retry && (await refreshSession())) {
      return apiRequest(path, { method, body, auth, retry: false });
    }
    endSession("expired");
    throw new ApiError("Your session has expired.", 401);
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status);
  return data;
}

const Api = {
  login: (email, password) =>
    apiRequest("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  signup: (email, password, roleId) =>
    apiRequest("/auth/signup", { method: "POST", body: { email, password, role_id: roleId }, auth: false }),

  listTasks: (params) => apiRequest(`/tasks/${queryString(params)}`),
  createTask: (task) => apiRequest("/tasks/", { method: "POST", body: task }),
  assignTask: (id, userId) =>
    apiRequest(`/tasks/${id}/assign`, { method: "PATCH", body: { assign_to_id: userId } }),
  updateTaskStatus: (id, status) =>
    apiRequest(`/tasks/${id}/status`, { method: "PATCH", body: { status } }),
  deleteTask: (id) => apiRequest(`/tasks/${id}`, { method: "DELETE" }),

  listUsers: (params) => apiRequest(`/users/${queryString(params)}`),
  listRoles: () => apiRequest("/roles/"),
};
