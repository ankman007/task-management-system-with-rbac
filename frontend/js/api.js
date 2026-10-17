// Thin wrapper around fetch() for the Task Management API.
//
// API_BASE is empty because the frontend is served by nginx on the same origin,
// which proxies /auth, /tasks and /users to the FastAPI container, so the
// browser never makes a cross-origin request.
const API_BASE = "";

class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

// Every API error has the shape { error: { code, message, details } }.
// For validation errors, details is a list of { field, message, type }.
function errorMessage(data, status) {
  const error = data && data.error;
  if (!error) return `Request failed (${status}).`;
  if (Array.isArray(error.details) && error.details.length) {
    return error.details.map((d) => String(d.message).replace(/^Value error, /, "")).join(" ");
  }
  return error.message;
}

function queryString(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") qs.set(key, value);
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function apiRequest(path, { method = "GET", body, form, auth = true } = {}) {
  const headers = {};
  let payload;
  if (form) {
    payload = new URLSearchParams(form);
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (auth) {
    const session = getSession();
    if (session) headers.Authorization = `Bearer ${session.access_token}`;
  }

  let res;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError("Can't reach the API. Is the backend running?", 0);
  }

  // Access tokens are short-lived and there is no refresh token: sign in again.
  if (res.status === 401 && auth) {
    endSession("expired");
    throw new ApiError("Your session has expired.", 401, "UNAUTHORIZED");
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, data?.error?.code);
  return data;
}

const Api = {
  // OAuth2 password flow: form-encoded, with the email sent as "username".
  login: (email, password) =>
    apiRequest("/auth/login", { method: "POST", form: { username: email, password }, auth: false }),
  register: (email, password) =>
    apiRequest("/auth/register", { method: "POST", body: { email, password }, auth: false }),
  me: (accessToken) =>
    fetch(`${API_BASE}/users/me`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((res) => (res.ok ? res.json() : Promise.reject(new ApiError("Could not load your profile.", res.status)))),

  // List endpoints return { items, total, page, size, pages }.
  listTasks: (params) => apiRequest(`/tasks${queryString(params)}`),
  createTask: (task) => apiRequest("/tasks", { method: "POST", body: task }),
  assignTask: (id, userId) =>
    apiRequest(`/tasks/${id}/assign`, { method: "PATCH", body: { assigned_to: userId } }),
  updateTaskStatus: (id, status) =>
    apiRequest(`/tasks/${id}/status`, { method: "PATCH", body: { status } }),
  deleteTask: (id) => apiRequest(`/tasks/${id}`, { method: "DELETE" }),

  listUsers: (params) => apiRequest(`/users${queryString(params)}`),
};
