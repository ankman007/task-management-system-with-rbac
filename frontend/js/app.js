// Dashboard app: routing, rendering and actions for index.html.

const PAGE_SIZE = 10;

const STATUS_LABELS = {
  PENDING: "Pending",
  IN_PROGRESS: "In progress",
  COMPLETED: "Completed",
};

const state = {
  user: null,
  role: null,
  page: null,
  users: new Map(), // id -> user; only admins can list users
  tasks: { skip: 0, search: "", status: "", items: [] },
  usersList: { skip: 0, search: "" },
  activeTask: null, // task targeted by the assign / delete dialogs
};

// What the current role may do. This only hides UI; the API enforces it.
const can = {
  createTask: () => state.role !== "USER",
  assignTask: () => state.role !== "USER",
  deleteTask: () => state.role === "ADMIN",
  viewAdmin: () => state.role === "ADMIN",
  updateStatus: (task) =>
    state.role === "ADMIN" ||
    task.assigned_to_id === state.user.id ||
    (state.role === "MANAGER" && task.created_by_id === state.user.id),
};

const PAGES = {
  dashboard: { title: "Dashboard", load: loadDashboard },
  tasks: { title: "Tasks", load: loadTasks },
  users: { title: "Users", load: loadUsers, adminOnly: true },
  roles: { title: "Roles", load: loadRoles, adminOnly: true },
};

// --- Small helpers -------------------------------------------------------------

const $ = (selector, root = document) => root.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function refreshIcons() {
  lucide.createIcons();
}

function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function toast(message, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<i data-lucide="${type === "success" ? "circle-check" : "circle-alert"}"></i><span></span>`;
  el.querySelector("span").textContent = message;
  $("#toasts").appendChild(el);
  refreshIcons();
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 200);
  }, 3500);
}

function roleBadge(role) {
  return `<span class="role-badge role-${role.toLowerCase()}">${role}</span>`;
}

function statusBadge(status) {
  return `<span class="badge badge-${status.toLowerCase()}">${STATUS_LABELS[status]}</span>`;
}

function avatar(text) {
  return `<span class="avatar">${escapeHtml(text.charAt(0))}</span>`;
}

function assigneeCell(id) {
  if (id == null) return `<span class="faint">Unassigned</span>`;
  if (id === state.user.id) return `<span class="person">${avatar(state.user.email)}You</span>`;
  const user = state.users.get(id);
  const label = user ? user.email : `User #${id}`;
  return `<span class="person">${avatar(label.replace("User #", "#"))}${escapeHtml(label)}</span>`;
}

function dueCell(task) {
  if (!task.due_date) return `<span class="faint">—</span>`;
  const date = new Date(task.due_date);
  const overdue = date < new Date() && task.status !== "COMPLETED";
  const label = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  return `<span class="due${overdue ? " overdue" : ""}" title="${overdue ? "Overdue" : ""}">${label}</span>`;
}

// --- Loading / empty / error states -------------------------------------------

function loadingState(columns = 5, rows = 4) {
  const cells = `<td><div class="skeleton"></div></td>`.repeat(columns);
  return `<table class="table"><tbody>${`<tr>${cells}</tr>`.repeat(rows)}</tbody></table>`;
}

function emptyState(icon, title, text) {
  return `<div class="state">
    <span class="state-icon"><i data-lucide="${icon}"></i></span>
    <h4>${title}</h4><p>${text}</p>
  </div>`;
}

function errorState(message) {
  return `<div class="state state-error">
    <span class="state-icon"><i data-lucide="triangle-alert"></i></span>
    <h4>Something went wrong</h4><p>${escapeHtml(message)}</p>
    <button class="btn btn-secondary" type="button" data-action="retry"><i data-lucide="rotate-cw"></i>Try again</button>
  </div>`;
}

function setPager(name, skip, count) {
  const pager = $(`#${name}-pager`);
  const hasPrev = skip > 0;
  const hasNext = count === PAGE_SIZE;
  pager.hidden = !hasPrev && !hasNext;
  $(`#${name}-range`).textContent = count ? `Showing ${skip + 1}–${skip + count}` : "No results on this page";
  pager.querySelector('[data-dir="-1"]').disabled = !hasPrev;
  pager.querySelector('[data-dir="1"]').disabled = !hasNext;
}

// --- Task table ----------------------------------------------------------------

function taskTable(tasks, withActions) {
  const rows = tasks.map((task) => {
    let actions = "";
    if (withActions) {
      const statusControl = can.updateStatus(task)
        ? `<select class="select status-select" data-id="${task.id}" data-current="${task.status}"
             aria-label="Change status" ${task.status === "COMPLETED" ? 'disabled title="Completed tasks are locked"' : ""}>
             ${Object.entries(STATUS_LABELS).map(([value, label]) =>
               `<option value="${value}" ${value === task.status ? "selected" : ""}>${label}</option>`).join("")}
           </select>`
        : "";
      const assignBtn = can.assignTask()
        ? `<button class="icon-btn" type="button" data-action="assign" data-id="${task.id}" title="Assign"><i data-lucide="user-plus"></i></button>`
        : "";
      const deleteBtn = can.deleteTask()
        ? `<button class="icon-btn danger" type="button" data-action="delete" data-id="${task.id}" title="Delete"><i data-lucide="trash-2"></i></button>`
        : "";
      actions = `<td><div class="row-actions">${statusControl}${assignBtn}${deleteBtn}</div></td>`;
    }

    return `<tr>
      <td><div class="task-title">${escapeHtml(task.title)}</div></td>
      <td class="col-desc"><div class="task-desc" title="${escapeHtml(task.description)}">${task.description ? escapeHtml(task.description) : '<span class="faint">—</span>'}</div></td>
      <td>${statusBadge(task.status)}</td>
      <td>${assigneeCell(task.assigned_to_id)}</td>
      <td>${dueCell(task)}</td>
      ${actions}
    </tr>`;
  }).join("");

  return `<table class="table">
    <thead><tr>
      <th>Task</th><th class="col-desc">Description</th><th>Status</th><th>Assignee</th><th>Due date</th>
      ${withActions ? '<th style="text-align:right">Actions</th>' : ""}
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// --- Dashboard -----------------------------------------------------------------

// The list endpoint caps limit at 100, so page through to count everything.
async function fetchAllTasks() {
  const all = [];
  for (let skip = 0; skip < 1000; skip += 100) {
    const batch = await Api.listTasks({ limit: 100, skip });
    all.push(...batch);
    if (batch.length < 100) break;
  }
  return all;
}

async function loadDashboard() {
  const scope = {
    ADMIN: "All tasks in the workspace.",
    MANAGER: "Tasks you created or that are assigned to you.",
    USER: "Tasks assigned to you.",
  };
  $("#greeting").textContent = `Welcome back, ${state.user.email.split("@")[0]}`;
  $("#dashboard-scope").textContent = scope[state.role];

  const recent = $("#recent-tasks");
  recent.innerHTML = loadingState(5, 5);

  try {
    const tasks = await fetchAllTasks();
    const count = (status) => tasks.filter((t) => t.status === status).length;
    $("#stat-total").textContent = tasks.length;
    $("#stat-pending").textContent = count("PENDING");
    $("#stat-progress").textContent = count("IN_PROGRESS");
    $("#stat-completed").textContent = count("COMPLETED");

    // Tasks have no created_at, so the highest IDs are the most recent.
    const latest = [...tasks].sort((a, b) => b.id - a.id).slice(0, 5);
    recent.innerHTML = latest.length
      ? taskTable(latest, false)
      : emptyState("inbox", "No tasks yet",
          can.createTask() ? "Create your first task to see it here." : "Tasks assigned to you will show up here.");
  } catch (err) {
    ["total", "pending", "progress", "completed"].forEach((id) => { $(`#stat-${id}`).textContent = "–"; });
    recent.innerHTML = errorState(err.message);
  }
  refreshIcons();
}

// --- Tasks page ----------------------------------------------------------------

async function loadTasks() {
  const container = $("#tasks-table");
  const { skip, search, status } = state.tasks;
  container.innerHTML = loadingState(6);
  $("#tasks-pager").hidden = true;

  try {
    const items = await Api.listTasks({ limit: PAGE_SIZE, skip, search, status });
    state.tasks.items = items;

    if (items.length) {
      container.innerHTML = taskTable(items, true);
    } else if (search || status) {
      container.innerHTML = emptyState("search-x", "No matching tasks", "Try a different search term or status.");
    } else {
      container.innerHTML = emptyState("inbox", "No tasks yet",
        can.createTask() ? "Click “New task” to create one." : "You don't have any tasks assigned to you yet.");
    }
    setPager("tasks", skip, items.length);
  } catch (err) {
    container.innerHTML = errorState(err.message);
  }
  refreshIcons();
}

async function changeStatus(select) {
  const id = Number(select.dataset.id);
  const previous = select.dataset.current;
  select.disabled = true;
  try {
    await Api.updateTaskStatus(id, select.value);
    toast(`Status changed to ${STATUS_LABELS[select.value]}.`);
    loadTasks();
  } catch (err) {
    select.value = previous;
    select.disabled = false;
    toast(err.message, "error");
  }
}

// --- Users page (admin) ----------------------------------------------------------

// Admins get a user directory so tasks can show emails and the assign
// dialogs can offer a dropdown.
async function loadUserDirectory() {
  try {
    for (let skip = 0; skip < 1000; skip += 100) {
      const batch = await Api.listUsers({ limit: 100, skip });
      batch.forEach((u) => state.users.set(u.id, u));
      if (batch.length < 100) break;
    }
  } catch {
    // Not fatal: tasks fall back to showing "User #id".
  }
}

async function loadUsers() {
  const container = $("#users-table");
  const { skip, search } = state.usersList;
  container.innerHTML = loadingState(3);
  $("#users-pager").hidden = true;

  try {
    const users = await Api.listUsers({ limit: PAGE_SIZE, skip, search });
    if (!users.length) {
      container.innerHTML = search
        ? emptyState("search-x", "No matching users", "No user email contains that text.")
        : emptyState("users", "No users yet", "Users appear here once they sign up.");
    } else {
      container.innerHTML = `<table class="table">
        <thead><tr><th>User</th><th>ID</th><th>Role</th></tr></thead>
        <tbody>${users.map((u) => `<tr>
          <td><span class="person">${avatar(u.email)}${escapeHtml(u.email)}${u.id === state.user.id ? ' <span class="faint">(you)</span>' : ""}</span></td>
          <td class="muted">#${u.id}</td>
          <td>${roleBadge(ROLE_NAMES[u.role_id] || `ROLE ${u.role_id}`)}</td>
        </tr>`).join("")}</tbody>
      </table>`;
    }
    setPager("users", skip, users.length);
  } catch (err) {
    container.innerHTML = errorState(err.message);
  }
  refreshIcons();
}

// --- Roles page (admin) ----------------------------------------------------------

const ROLE_INFO = {
  ADMIN: { icon: "crown", text: "Full access to every task, plus user and role administration." },
  MANAGER: { icon: "briefcase", text: "Creates and assigns tasks, and manages the ones they own or are assigned." },
  USER: { icon: "user", text: "Sees and updates the status of tasks assigned to them." },
};

// Mirrors the checks in app/services/*.
const PERMISSIONS = [
  ["View tasks", ["All", "Created or assigned", "Assigned only"]],
  ["Create tasks", [true, true, false]],
  ["Assign tasks", [true, true, false]],
  ["Update task status", ["All", "Created or assigned", "Assigned only"]],
  ["Delete tasks", [true, false, false]],
  ["View users", [true, false, false]],
  ["View roles", [true, false, false]],
];

function permissionCell(value) {
  if (value === true) return `<i data-lucide="check" class="yes"></i>`;
  if (value === false) return `<i data-lucide="minus" class="no"></i>`;
  return `<i data-lucide="check" class="yes"></i><span class="scope">${value}</span>`;
}

async function loadRoles() {
  const list = $("#roles-list");
  list.innerHTML = `<div class="card">${loadingState(3, 3)}</div>`;

  $("#permissions-matrix").innerHTML = PERMISSIONS.map(([action, values]) =>
    `<tr><td>${action}</td>${values.map((v) => `<td>${permissionCell(v)}</td>`).join("")}</tr>`
  ).join("");

  try {
    const roles = await Api.listRoles();
    const members = (roleId) => [...state.users.values()].filter((u) => u.role_id === roleId).length;
    list.innerHTML = `<div class="role-grid">${roles.map((role) => {
      const info = ROLE_INFO[role.name] || { icon: "shield", text: "" };
      const n = members(role.id);
      return `<div class="card role-card">
        <div class="role-card-head">
          <span class="stat-icon"><i data-lucide="${info.icon}"></i></span>
          ${roleBadge(role.name)}
        </div>
        <h3>${role.name.charAt(0) + role.name.slice(1).toLowerCase()}</h3>
        <p>${info.text}</p>
        <p class="faint" style="margin-top:12px">${n} ${n === 1 ? "member" : "members"} · ID ${role.id}</p>
      </div>`;
    }).join("")}</div>`;
  } catch (err) {
    list.innerHTML = `<div class="card" style="margin-bottom:24px">${errorState(err.message)}</div>`;
  }
  refreshIcons();
}

// --- Dialogs -------------------------------------------------------------------

// Admins pick from the user directory; managers can't list users, so they enter an ID.
function assigneeField(container, { required, selectedId }) {
  const optional = required ? "" : ' <span class="faint">(optional)</span>';
  if (can.viewAdmin() && state.users.size) {
    const options = [...state.users.values()].map((u) =>
      `<option value="${u.id}" ${u.id === selectedId ? "selected" : ""}>${escapeHtml(u.email)} · ${ROLE_NAMES[u.role_id] || ""}</option>`
    ).join("");
    container.innerHTML = `<label for="${container.closest("dialog").id}-assignee">Assignee${optional}</label>
      <select class="select" id="${container.closest("dialog").id}-assignee" name="assignee" ${required ? "required" : ""}>
        ${required ? "" : '<option value="">Unassigned</option>'}${options}
      </select>`;
  } else {
    container.innerHTML = `<label for="${container.closest("dialog").id}-assignee">Assignee user ID${optional}</label>
      <input class="input" id="${container.closest("dialog").id}-assignee" name="assignee" type="number" min="1"
        placeholder="e.g. 3" value="${selectedId ?? ""}" ${required ? "required" : ""}>
      <span class="hint">Only admins can browse users, so enter the user's ID.</span>`;
  }
}

function openDialog(dialog) {
  const error = $(".form-error", dialog);
  if (error) error.hidden = true;
  dialog.showModal();
  refreshIcons();
}

function openCreateDialog() {
  const dialog = $("#create-dialog");
  const form = $("#create-form");
  form.reset();
  // datetime-local wants local time without seconds or zone
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  form.due.min = now.toISOString().slice(0, 16);
  assigneeField($(".assignee-field", form), { required: false });
  openDialog(dialog);
  form.elements.title.focus();
}

function openAssignDialog(task) {
  state.activeTask = task;
  $("#assign-task-name").innerHTML = `Choose who should work on <strong>${escapeHtml(task.title)}</strong>.`;
  assigneeField($("#assign-form .assignee-field"), { required: true, selectedId: task.assigned_to_id });
  openDialog($("#assign-dialog"));
}

function openDeleteDialog(task) {
  state.activeTask = task;
  $("#delete-task-name").innerHTML = `<strong>${escapeHtml(task.title)}</strong> will be permanently deleted. This can't be undone.`;
  openDialog($("#delete-dialog"));
}

// Runs a dialog's submit action with a busy button and inline errors.
async function submitDialog(form, busyLabel, action) {
  const dialog = form.closest("dialog");
  const error = $(".form-error", dialog);
  const button = form.querySelector("button[type=submit]");
  error.hidden = true;
  setButtonBusy(button, true, busyLabel);
  try {
    const message = await action();
    dialog.close();
    toast(message);
    PAGES[state.page].load();
  } catch (err) {
    if (err.status !== 401) showFormError(error, err.message);
  } finally {
    setButtonBusy(button, false);
  }
}

// --- Routing and events ----------------------------------------------------------

function route() {
  let page = location.hash.slice(1) || "dashboard";
  if (!PAGES[page]) page = "dashboard";
  if (PAGES[page].adminOnly && !can.viewAdmin()) {
    toast("That page is only available to admins.", "error");
    page = "dashboard";
    history.replaceState(null, "", "#dashboard");
  }

  state.page = page;
  document.querySelectorAll(".page").forEach((el) => { el.hidden = el.id !== `page-${page}`; });
  document.querySelectorAll(".nav-link").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  $("#page-title").textContent = PAGES[page].title;
  document.title = `${PAGES[page].title} · Task Manager`;
  $("#new-task-btn").hidden = !(can.createTask() && (page === "dashboard" || page === "tasks"));
  closeSidebar();
  PAGES[page].load();
}

function closeSidebar() {
  $("#sidebar").classList.remove("open");
  $("#backdrop").classList.remove("show");
}

function renderSidebar() {
  $("#user-avatar").textContent = state.user.email.charAt(0);
  $("#user-email").textContent = state.user.email;
  $("#user-role").innerHTML = roleBadge(state.role);
  $(".admin-only").hidden = !can.viewAdmin();
}

function findTask(id) {
  return state.tasks.items.find((t) => t.id === id);
}

function bindEvents() {
  window.addEventListener("hashchange", route);

  $("#logout-btn").addEventListener("click", () => endSession());
  $("#menu-btn").addEventListener("click", () => {
    $("#sidebar").classList.add("open");
    $("#backdrop").classList.add("show");
  });
  $("#backdrop").addEventListener("click", closeSidebar);
  $("#new-task-btn").addEventListener("click", openCreateDialog);

  // Retry buttons inside error states reload the current page.
  document.addEventListener("click", (event) => {
    if (event.target.closest('[data-action="retry"]')) PAGES[state.page].load();
  });

  // Task row actions
  $("#tasks-table").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || button.dataset.action === "retry") return;
    const task = findTask(Number(button.dataset.id));
    if (!task) return;
    if (button.dataset.action === "assign") openAssignDialog(task);
    if (button.dataset.action === "delete") openDeleteDialog(task);
  });
  $("#tasks-table").addEventListener("change", (event) => {
    if (event.target.matches(".status-select")) changeStatus(event.target);
  });

  // Filters
  $("#task-search").addEventListener("input", debounce((event) => {
    state.tasks.search = event.target.value.trim();
    state.tasks.skip = 0;
    loadTasks();
  }));
  $("#task-status-filter").addEventListener("change", (event) => {
    state.tasks.status = event.target.value;
    state.tasks.skip = 0;
    loadTasks();
  });
  $("#user-search").addEventListener("input", debounce((event) => {
    state.usersList.search = event.target.value.trim();
    state.usersList.skip = 0;
    loadUsers();
  }));

  // Pagination
  document.querySelectorAll("[data-pager]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.pager;
      const target = name === "tasks" ? state.tasks : state.usersList;
      target.skip = Math.max(0, target.skip + Number(button.dataset.dir) * PAGE_SIZE);
      name === "tasks" ? loadTasks() : loadUsers();
    });
  });

  // Dialog close buttons
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });

  // Create task
  $("#create-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target;
    const error = $(".form-error", form);
    const title = form.elements.title.value.trim();
    if (!title) {
      showFormError(error, "Title is required.");
      return;
    }

    const task = { title };
    if (form.description.value.trim()) task.description = form.description.value.trim();
    if (form.due.value) task.due_date = new Date(form.due.value).toISOString();
    if (form.assignee.value) task.assigned_to_id = Number(form.assignee.value);

    submitDialog(form, "Creating…", async () => {
      await Api.createTask(task);
      return "Task created.";
    });
  });

  // Assign task
  $("#assign-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target;
    const userId = Number(form.assignee.value);
    if (!userId) {
      showFormError($(".form-error", form), "Choose a user to assign.");
      return;
    }
    submitDialog(form, "Assigning…", async () => {
      await Api.assignTask(state.activeTask.id, userId);
      return "Task assigned.";
    });
  });

  // Delete task
  $("#delete-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitDialog(event.target, "Deleting…", async () => {
      await Api.deleteTask(state.activeTask.id);
      return "Task deleted.";
    });
  });
}

// --- Start ---------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireSession()) return;

  state.user = getSession().user;
  state.role = ROLE_NAMES[state.user.role_id] || "USER";

  renderSidebar();
  bindEvents();
  refreshIcons();

  if (can.viewAdmin()) await loadUserDirectory();
  route();
});
