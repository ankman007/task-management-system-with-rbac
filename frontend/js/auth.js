// Session storage plus the login and signup page logic.

const SESSION_KEY = "task_manager_session";

function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

function saveSession({ access_token, user }) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ access_token, user }));
}

// Log in, then load the profile (id, email, role) the dashboard needs.
async function signIn(email, password) {
  const { access_token } = await Api.login(email, password);
  const user = await Api.me(access_token);
  saveSession({ access_token, user });
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function requireSession() {
  const session = getSession();
  if (!session || !session.access_token || !session.user) {
    location.replace("login.html");
    return false;
  }
  return true;
}

function endSession(reason) {
  clearSession();
  location.replace(reason ? `login.html?reason=${reason}` : "login.html");
}

// --- Shared form helpers ---------------------------------------------------

function showFormError(el, message) {
  el.innerHTML = `<i data-lucide="circle-alert"></i><span></span>`;
  el.querySelector("span").textContent = message;
  el.hidden = false;
  lucide.createIcons();
}

function setButtonBusy(button, busy, busyLabel) {
  if (busy) {
    button.dataset.label = button.innerHTML;
    button.innerHTML = `<span class="spinner"></span>${busyLabel}`;
    button.disabled = true;
  } else {
    button.innerHTML = button.dataset.label;
    button.disabled = false;
  }
}

// --- Login page --------------------------------------------------------------

function initLoginPage() {
  const form = document.getElementById("login-form");
  const error = document.getElementById("form-error");
  const notice = document.getElementById("form-notice");

  if (new URLSearchParams(location.search).get("reason") === "expired") {
    notice.hidden = false;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const button = form.querySelector("button[type=submit]");
    setButtonBusy(button, true, "Signing in…");

    try {
      await signIn(form.email.value.trim(), form.password.value);
      location.replace("index.html");
    } catch (err) {
      showFormError(error, err.message);
      setButtonBusy(button, false);
    }
  });
}

// --- Signup page -------------------------------------------------------------

function initSignupPage() {
  const form = document.getElementById("signup-form");
  const error = document.getElementById("form-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;

    if (form.password.value !== form.confirm.value) {
      showFormError(error, "Passwords don't match.");
      return;
    }

    const button = form.querySelector("button[type=submit]");
    setButtonBusy(button, true, "Creating account…");

    try {
      const email = form.email.value.trim();
      await Api.register(email, form.password.value);
      await signIn(email, form.password.value);
      location.replace("index.html");
    } catch (err) {
      showFormError(error, err.message);
      setButtonBusy(button, false);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page !== "login" && page !== "signup") return;

  // Already signed in: go straight to the dashboard.
  if (getSession()?.access_token) {
    location.replace("index.html");
    return;
  }
  if (page === "login") initLoginPage();
  if (page === "signup") initSignupPage();
  lucide.createIcons();
});
