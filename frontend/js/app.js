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
  users: new Map(), // id -> user; admins and managers can list users
  tasks: { page: 1, status: "", items: [] },
  usersList: { page: 1 },
  activeTask: null, // task targeted by the assign / delete dialogs
};

// What the current role may do. This only hides UI; the API enforces it.
const can = {
  createTask: () => state.role !== "USER",
  assignTask: (task) => state.role === "ADMIN" || (state.role === "MANAGER" && ownsTask(task)),
  deleteTask: () => state.role === "ADMIN",
  viewAdmin: () => state.role === "ADMIN",
  listUsers: () => state.role !== "USER",
  updateStatus: (task) =>
    state.role === "ADMIN" ||
    task.assigned_to === state.user.id ||
    (state.role === "MANAGER" && task.created_by === state.user.id),
};

function ownsTask(task) {
  return task.created_by === state.user.id || task.assigned_to === state.user.id;
}

// Mirrors ALLOWED_TRANSITIONS in app/services/task_service.py.
const TRANSITIONS = {
  PENDING: ["IN_PROGRESS", "COMPLETED"],
  IN_PROGRESS: ["PENDING", "COMPLETED"],
  COMPLETED: ["IN_PROGRESS"],
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

function setPager(name, { page, size, total, pages, items }) {
  const pager = $(`#${name}-pager`);
  const hasPrev = page > 1;
  const hasNext = page < pages;
  const start = (page - 1) * size;
  pager.hidden = !hasPrev && !hasNext;
  $(`#${name}-range`).textContent = items.length
    ? `Showing ${start + 1}–${start + items.length} of ${total}`
    : "No results on this page";
  pager.querySelector('[data-dir="-1"]').disabled = !hasPrev;
  pager.querySelector('[data-dir="1"]').disabled = !hasNext;
}

// --- Task table ----------------------------------------------------------------

function taskTable(tasks, withActions) {
  const rows = tasks.map((task) => {
    let actions = "";
    if (withActions) {
      const statusControl = can.updateStatus(task)
        ? `<select class="select status-select" data-id="${task.id}" data-current="${task.status}" aria-label="Change status">
             ${[task.status, ...TRANSITIONS[task.status]].map((value) =>
               `<option value="${value}" ${value === task.status ? "selected" : ""}>${STATUS_LABELS[value]}</option>`).join("")}
           </select>`
        : "";
      const assignBtn = can.assignTask(task)
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
      <td>${assigneeCell(task.assigned_to)}</td>
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
    // Each list response carries a total, so counting needs no full fetch.
    // The API returns tasks newest first.
    const total = (status) => Api.listTasks({ status, size: 1 }).then((p) => p.total);
    const [latestPage, pending, progress, completed] = await Promise.all([
      Api.listTasks({ size: 5 }), total("PENDING"), total("IN_PROGRESS"), total("COMPLETED"),
    ]);
    $("#stat-total").textContent = latestPage.total;
    $("#stat-pending").textContent = pending;
    $("#stat-progress").textContent = progress;
    $("#stat-completed").textContent = completed;

    const latest = latestPage.items;
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
  const { page, status } = state.tasks;
  container.innerHTML = loadingState(6);
  $("#tasks-pager").hidden = true;

  try {
    const result = await Api.listTasks({ page, size: PAGE_SIZE, status });
    const items = result.items;
    state.tasks.items = items;

    if (items.length) {
      container.innerHTML = taskTable(items, true);
    } else if (status) {
      container.innerHTML = emptyState("search-x", "No matching tasks", "Try a different status.");
    } else {
      container.innerHTML = emptyState("inbox", "No tasks yet",
        can.createTask() ? "Click “New task” to create one." : "You don't have any tasks assigned to you yet.");
    }
    setPager("tasks", result);
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

// Admins and managers get a user directory so tasks can show emails and the
// assign dialogs can offer a dropdown.
async function loadUserDirectory() {
  try {
    for (let page = 1; page <= 10; page += 1) {
      const result = await Api.listUsers({ page, size: 100 });
      result.items.forEach((u) => state.users.set(u.id, u));
      if (page >= result.pages) break;
    }
  } catch {
    // Not fatal: tasks fall back to showing "User #id".
  }
}

async function loadUsers() {
  const container = $("#users-table");
  const { page } = state.usersList;
  container.innerHTML = loadingState(3);
  $("#users-pager").hidden = true;

  try {
    const result = await Api.listUsers({ page, size: PAGE_SIZE });
    const users = result.items;
    if (!users.length) {
      container.innerHTML = emptyState("users", "No users yet", "Users appear here once they sign up.");
    } else {
      container.innerHTML = `<table class="table">
        <thead><tr><th>User</th><th>ID</th><th>Role</th></tr></thead>
        <tbody>${users.map((u) => `<tr>
          <td><span class="person">${avatar(u.email)}${escapeHtml(u.email)}${u.id === state.user.id ? ' <span class="faint">(you)</span>' : ""}</span></td>
          <td class="muted">#${u.id}</td>
          <td>${roleBadge(u.role)}</td>
        </tr>`).join("")}</tbody>
      </table>`;
    }
    setPager("users", result);
  } catch (err) {
    container.innerHTML = errorState(err.message);
  }
  refreshIcons();
}

// --- Roles page (admin) ----------------------------------------------------------

const ROLE_INFO = {
  ADMIN: { icon: "crown", text: "Full access to every task, including deleting tasks." },
  MANAGER: { icon: "briefcase", text: "Creates and assigns tasks, and manages the ones they own or are assigned." },
  USER: { icon: "user", text: "Sees and updates the status of tasks assigned to them." },
};

// Mirrors the checks in app/services/*.
const PERMISSIONS = [
  ["View tasks", ["All", "Created or assigned", "Assigned only"]],
  ["Create tasks", [true, true, false]],
  ["Assign tasks", ["All", "Created or assigned", false]],
  ["Update task status", ["All", "Created or assigned", "Assigned only"]],
  ["Delete tasks", [true, false, false]],
  ["View users", [true, true, false]],
];

function permissionCell(value) {
  if (value === true) return `<i data-lucide="check" class="yes"></i>`;
  if (value === false) return `<i data-lucide="minus" class="no"></i>`;
  return `<i data-lucide="check" class="yes"></i><span class="scope">${value}</span>`;
}

function loadRoles() {
  const list = $("#roles-list");

  $("#permissions-matrix").innerHTML = PERMISSIONS.map(([action, values]) =>
    `<tr><td>${action}</td>${values.map((v) => `<td>${permissionCell(v)}</td>`).join("")}</tr>`
  ).join("");

  // Roles are fixed (seeded by a migration), so they are described statically.
  const members = (role) => [...state.users.values()].filter((u) => u.role === role).length;
  list.innerHTML = `<div class="role-grid">${Object.entries(ROLE_INFO).map(([role, info]) => {
    const n = members(role);
    return `<div class="card role-card">
      <div class="role-card-head">
        <span class="stat-icon"><i data-lucide="${info.icon}"></i></span>
        ${roleBadge(role)}
      </div>
      <h3>${role.charAt(0) + role.slice(1).toLowerCase()}</h3>
      <p>${info.text}</p>
      <p class="faint" style="margin-top:12px">${n} ${n === 1 ? "member" : "members"}</p>
    </div>`;
  }).join("")}</div>`;
  refreshIcons();
}

// --- Dialogs -------------------------------------------------------------------

// Pick from the user directory; fall back to an ID field if it couldn't load.
function assigneeField(container, { required, selectedId }) {
  const optional = required ? "" : ' <span class="faint">(optional)</span>';
  if (state.users.size) {
    const options = [...state.users.values()].map((u) =>
      `<option value="${u.id}" ${u.id === selectedId ? "selected" : ""}>${escapeHtml(u.email)} · ${u.role}</option>`
    ).join("");
    container.innerHTML = `<label for="${container.closest("dialog").id}-assignee">Assignee${optional}</label>
      <select class="select" id="${container.closest("dialog").id}-assignee" name="assignee" ${required ? "required" : ""}>
        ${required ? "" : '<option value="">Unassigned</option>'}${options}
      </select>`;
  } else {
    container.innerHTML = `<label for="${container.closest("dialog").id}-assignee">Assignee user ID${optional}</label>
      <input class="input" id="${container.closest("dialog").id}-assignee" name="assignee" type="number" min="1"
        placeholder="e.g. 3" value="${selectedId ?? ""}" ${required ? "required" : ""}>
      <span class="hint">The user list couldn't be loaded, so enter the user's ID.</span>`;
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
  // The API rejects due dates in the past; <input type=date> wants YYYY-MM-DD.
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  form.due.min = today.toISOString().slice(0, 10);
  assigneeField($(".assignee-field", form), { required: false });
  openDialog(dialog);
  form.elements.title.focus();
}

function openAssignDialog(task) {
  state.activeTask = task;
  $("#assign-task-name").innerHTML = `Choose who should work on <strong>${escapeHtml(task.title)}</strong>.`;
  assigneeField($("#assign-form .assignee-field"), { required: true, selectedId: task.assigned_to });
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
  $("#task-status-filter").addEventListener("change", (event) => {
    state.tasks.status = event.target.value;
    state.tasks.page = 1;
    loadTasks();
  });

  // Pagination
  document.querySelectorAll("[data-pager]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.pager;
      const target = name === "tasks" ? state.tasks : state.usersList;
      target.page = Math.max(1, target.page + Number(button.dataset.dir));
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
    if (form.due.value) task.due_date = form.due.value;
    if (form.assignee.value) task.assigned_to = Number(form.assignee.value);

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
  state.role = state.user.role;

  renderSidebar();
  bindEvents();
  refreshIcons();

  if (can.listUsers()) await loadUserDirectory();
  route();
});
