const state = {
  apps: [],
  runtime: null,
  lastScreenStamp: "",
};

async function fetchJson(url, options = {}) {
  const timeoutMs = options.timeoutMs || 0;
  const controller = timeoutMs ? new AbortController() : null;
  const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
      signal: controller ? controller.signal : options.signal,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Request failed: ${response.status}`);
    }
    return payload;
  } finally {
    if (timer) {
      window.clearTimeout(timer);
    }
  }
}

function setRuntime(runtime) {
  state.runtime = runtime;
  const el = document.getElementById("runtimeSummary");
  el.textContent = `${runtime.device_serial} • ${runtime.model_provider} • ${runtime.vision_model}`;
  document.getElementById("providerSelect").value = runtime.model_provider;
  document.getElementById("geminiModelInput").value = runtime.gemini_model || "";
  document.getElementById("lmstudioModelInput").value = runtime.lmstudio_model || "";
}

function renderApps(apps) {
  state.apps = apps;
  const select = document.getElementById("appSelect");
  const list = document.getElementById("appsList");
  const selectedValue = select.value;
  select.innerHTML = "";
  list.innerHTML = "";
  for (const app of apps) {
    const option = document.createElement("option");
    option.value = app.name;
    option.textContent = `${app.name} (${app.package_name})`;
    select.appendChild(option);

    const card = document.createElement("article");
    card.className = "app-card";
    card.innerHTML = `
      <strong>${app.name}</strong>
      <div class="muted">${app.package_name}</div>
      <p class="muted">${app.default_goal_hint}</p>
    `;
    card.addEventListener("click", () => {
      select.value = app.name;
      document.getElementById("goalInput").value = app.default_goal_hint;
    });
    list.appendChild(card);
  }
  if (selectedValue && apps.some((app) => app.name === selectedValue)) {
    select.value = selectedValue;
  }
  if (apps[0] && !document.getElementById("goalInput").value.trim()) {
    document.getElementById("goalInput").value = apps[0].default_goal_hint;
  }
}

function renderScreen(payload) {
  const screen = payload.screen;
  const image = document.getElementById("screenImage");
  const frame = image.parentElement;
  const meta = document.getElementById("screenMeta");
  const visible = document.getElementById("visibleTextList");
  const clickable = document.getElementById("clickableTextList");
  if (!screen) {
    meta.textContent = "No screen capture yet.";
    frame.classList.add("is-empty");
    image.removeAttribute("src");
    visible.innerHTML = "";
    clickable.innerHTML = "";
    return;
  }
  const stamp = `${screen.screenshot_path || ""}:${screen.package_name || ""}:${screen.activity_name || ""}`;
  if (stamp !== state.lastScreenStamp) {
    image.src = `/api/device/screenshot?ts=${Date.now()}`;
    state.lastScreenStamp = stamp;
  }
  frame.classList.remove("is-empty");
  if (screen.device?.width && screen.device?.height) {
    image.style.aspectRatio = `${screen.device.width} / ${screen.device.height}`;
  }
  meta.textContent = `${screen.package_name || "unknown package"} • ${screen.activity_name || "unknown activity"}`;
  visible.innerHTML = "";
  clickable.innerHTML = "";
  for (const value of (screen.visible_text || []).slice(0, 12)) {
    const li = document.createElement("li");
    li.textContent = value;
    visible.appendChild(li);
  }
  for (const value of (screen.clickable_text || []).slice(0, 12)) {
    const li = document.createElement("li");
    li.textContent = value;
    clickable.appendChild(li);
  }
}

function renderJob(job) {
  const badge = document.getElementById("jobBadge");
  const summary = document.getElementById("jobSummary");
  const payload = document.getElementById("jobPayload");
  const log = document.getElementById("eventLog");
  if (!job) {
    badge.textContent = "Idle";
    summary.textContent = "No active task.";
    payload.textContent = "";
    log.innerHTML = "";
    document.querySelectorAll("[data-tool], #launchAppButton, #startTaskButton").forEach((button) => {
      button.disabled = false;
    });
    return;
  }
  badge.textContent = job.status;
  summary.textContent = `${job.app_name} • ${job.goal}`;
  payload.textContent = JSON.stringify(job.payload || {
    task_id: job.task_id,
    status: job.status,
    run_dir: job.run_dir,
    last_reason: job.last_reason,
  }, null, 2);
  log.innerHTML = "";
  for (const entry of (job.events || []).slice().reverse()) {
    const li = document.createElement("li");
    const detail = JSON.stringify(entry, null, 2);
    li.textContent = detail;
    log.appendChild(li);
  }
  const busy = job.status === "running";
  document.querySelectorAll("[data-tool], #launchAppButton, #startTaskButton").forEach((button) => {
    button.disabled = busy;
  });
}

function renderTasks(tasks) {
  const root = document.getElementById("tasksTable");
  root.innerHTML = "";
  for (const task of tasks) {
    const item = document.createElement("article");
    item.className = "task-row";
    item.innerHTML = `
      <header>
        <strong>${task.app_name}</strong>
        <span class="status-${task.status}">${task.status}</span>
      </header>
      <div>${task.goal}</div>
      <div class="muted">${task.task_id}</div>
      <div class="muted">steps: ${task.total_steps} • yolo: ${task.yolo_mode ? "on" : "off"}</div>
      <div class="task-actions"></div>
    `;
    const actions = item.querySelector(".task-actions");
    if (["ready", "ready_to_resume", "waiting_for_login", "waiting_for_verification", "waiting_for_manual"].includes(task.status)) {
      const resume = document.createElement("button");
      resume.className = "secondary";
      resume.textContent = "Resume";
      resume.addEventListener("click", () => resumeTask(task.task_id));
      actions.appendChild(resume);
    }
    if (!["completed", "canceled"].includes(task.status)) {
      const cancel = document.createElement("button");
      cancel.className = "secondary";
      cancel.textContent = "Cancel";
      cancel.addEventListener("click", () => cancelTask(task.task_id));
      actions.appendChild(cancel);
    }
    root.appendChild(item);
  }
}

async function refreshAll() {
  fetchJson("/api/runtime").then(setRuntime).catch(console.error);
  fetchJson("/api/apps").then(renderApps).catch(console.error);
  fetchJson("/api/tasks").then(renderTasks).catch(console.error);
  fetchJson("/api/job").then(renderJob).catch(console.error);
  fetchJson("/api/device/state", { timeoutMs: 1500 })
    .then((payload) => {
      renderScreen(payload);
      const meta = document.getElementById("screenMeta");
      if (payload.screen_error) {
        meta.textContent = `Mirror unavailable: ${payload.screen_error}`;
        document.getElementById("screenImage").parentElement.classList.add("is-empty");
      }
    })
    .catch((error) => {
      const meta = document.getElementById("screenMeta");
      meta.textContent = `Mirror unavailable: ${error.message || String(error)}`;
      document.getElementById("screenImage").parentElement.classList.add("is-empty");
    });
}

async function startTask() {
  const payload = {
    app_name: document.getElementById("appSelect").value,
    goal: document.getElementById("goalInput").value,
    max_steps: Number(document.getElementById("maxStepsInput").value || 8),
    yolo_mode: document.getElementById("yoloInput").checked,
  };
  await fetchJson("/api/tasks/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshAll();
}

async function resumeTask(taskId) {
  const payload = {
    max_steps: Number(document.getElementById("maxStepsInput").value || 8),
    yolo_mode: document.getElementById("yoloInput").checked,
  };
  await fetchJson(`/api/tasks/${taskId}/resume`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshAll();
}

async function cancelTask(taskId) {
  await fetchJson(`/api/tasks/${taskId}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  await refreshAll();
}

async function runTool(toolName) {
  const payload = {
    tool_name: toolName,
    app_name: document.getElementById("appSelect").value,
    arguments: {},
  };
  await fetchJson("/api/tools/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshAll();
}

async function launchSelectedApp() {
  const payload = {
    tool_name: "launch_app",
    app_name: document.getElementById("appSelect").value,
    arguments: {},
  };
  await fetchJson("/api/tools/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshAll();
}

async function saveModelSettings() {
  const payload = {
    model_provider: document.getElementById("providerSelect").value,
    gemini_model: document.getElementById("geminiModelInput").value,
    lmstudio_model: document.getElementById("lmstudioModelInput").value,
  };
  await fetchJson("/api/settings/model", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshAll();
}

function attachHandlers() {
  document.getElementById("startTaskButton").addEventListener("click", () => startTask().catch(showError));
  document.getElementById("launchAppButton").addEventListener("click", () => launchSelectedApp().catch(showError));
  document.getElementById("refreshButton").addEventListener("click", () => refreshAll().catch(showError));
  document.getElementById("saveModelButton").addEventListener("click", () => saveModelSettings().catch(showError));
  document.querySelectorAll("[data-tool]").forEach((button) => {
    button.addEventListener("click", () => runTool(button.dataset.tool).catch(showError));
  });
}

function showError(error) {
  window.alert(error.message || String(error));
}

async function boot() {
  attachHandlers();
  await refreshAll();
  window.setInterval(() => {
    refreshAll().catch(console.error);
  }, 2500);
}

boot().catch(showError);
