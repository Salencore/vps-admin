const state = {
  token: localStorage.getItem("vps_admin_token") || "",
};

const $ = (selector) => document.querySelector(selector);

function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  return fetch(path, { ...options, headers }).then(async (response) => {
    if (!response.ok) throw new Error((await response.text()) || response.statusText);
    return response;
  });
}

function showApp() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  refreshAll();
}

function showLogin() {
  $("#login").classList.remove("hidden");
  $("#app").classList.add("hidden");
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unit]}`;
}

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return `${days}d ${hours}h`;
}

async function loadOverview() {
  const data = await api("/api/overview").then((r) => r.json());
  $("#host-line").textContent = `${data.hostname} · ${data.platform}`;
  $("#cpu").textContent = `${data.cpu_percent}%`;
  $("#ram").textContent = `${data.memory.percent}%`;
  $("#disk").textContent = `${data.disk.percent}%`;
  $("#uptime").textContent = formatUptime(data.uptime_seconds);
}

async function loadContainers() {
  const items = await api("/api/docker/containers").then((r) => r.json());
  $("#container-list").innerHTML = items
    .map(
      (item) => `
        <article class="item">
          <div class="item-row">
            <strong>${item.name}</strong>
            <span>${item.status}${item.health ? ` · ${item.health}` : ""}</span>
          </div>
          <span>${item.image}</span>
          <span>CPU ${item.stats?.cpu_percent ?? 0}% · RAM ${item.stats?.memory_percent ?? 0}%</span>
          <div class="actions">
            <button data-log="${item.id}">Логи</button>
            <button data-action="start" data-id="${item.id}">Start</button>
            <button data-action="stop" data-id="${item.id}">Stop</button>
            <button data-action="restart" data-id="${item.id}">Restart</button>
          </div>
        </article>
      `,
    )
    .join("");
}

async function loadSecurity() {
  const items = await api("/api/security/events").then((r) => r.json());
  $("#security-list").innerHTML = items
    .map((item) => `<article class="item"><strong>${item.event_type}</strong><span>${item.username || "-"} · ${item.ip || "-"}</span><span>${item.occurred_at}</span></article>`)
    .join("");
}

async function loadAudit() {
  const items = await api("/api/audit").then((r) => r.json());
  $("#audit-list").innerHTML = items
    .map((item) => `<article class="item"><strong>${item.action}</strong><span>${item.actor} · ${item.target || "-"}</span><span>${item.created_at}</span></article>`)
    .join("");
}

async function loadSettings() {
  const data = await api("/api/settings").then((r) => r.json());
  const form = $("#settings-form");
  Object.entries(data).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });
}

async function refreshAll() {
  await Promise.allSettled([loadOverview(), loadContainers(), loadSecurity(), loadAudit(), loadSettings()]);
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
    }).then((r) => r.json());
    state.token = data.access_token;
    localStorage.setItem("vps_admin_token", state.token);
    showApp();
  } catch {
    $("#login-error").textContent = "Неверный логин или пароль";
  }
});

$("#logout").addEventListener("click", () => {
  state.token = "";
  localStorage.removeItem("vps_admin_token");
  showLogin();
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.tab) {
    document.querySelectorAll(".tabs button").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    $(`#${button.dataset.tab}`).classList.add("active");
  }
  if (button.dataset.log) {
    $("#logs").textContent = await api(`/api/docker/containers/${button.dataset.log}/logs`).then((r) => r.text());
  }
  if (button.dataset.action) {
    await api(`/api/docker/containers/${button.dataset.id}/${button.dataset.action}`, { method: "POST" });
    await loadContainers();
  }
});

$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  ["cpu_alert_percent", "ram_alert_percent", "disk_alert_percent"].forEach((key) => {
    payload[key] = Number(payload[key]);
  });
  await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
});

if (state.token) showApp();
else showLogin();

setInterval(() => {
  if (state.token) refreshAll();
}, 30000);
