const state = {
  system: "offline",
  readers: [],
  logs: [],
  wsOnline: false,
};

const readersGrid = document.getElementById("readersGrid");
const logsList = document.getElementById("logsList");
const refreshButton = document.getElementById("refreshButton");
const systemState = document.getElementById("systemState");
const readerCount = document.getElementById("readerCount");
const lastEventTime = document.getElementById("lastEventTime");
const socketBadge = document.getElementById("socketBadge");
const systemOnlinePill = document.getElementById("systemOnlinePill");

let socket = null;
let reconnectTimer = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTimestamp(value) {
  if (!value) {
    return "Never";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusClass(status) {
  return `status-${status || "disconnected"}`;
}

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `HTTP ${response.status}`);
  }
  return response.json();
}

async function loadInitialData() {
  const [status, logs] = await Promise.all([
    fetchJson("/api/status"),
    fetchJson("/api/logs"),
  ]);
  state.system = status.system;
  state.readers = status.readers;
  state.logs = logs;
  render();
}

async function runReaderAction(readerId, action) {
  const button = document.querySelector(`[data-reader-action="${action}:${readerId}"]`);
  if (button) {
    button.disabled = true;
  }
  try {
    await fetchJson(`/api/readers/${readerId}/${action}`, { method: "POST" });
    await loadInitialData();
  } catch (error) {
    window.alert(`Action failed: ${error.message}`);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

function renderSystem() {
  systemState.textContent = state.system;
  readerCount.textContent = String(state.readers.length);
  lastEventTime.textContent = state.logs.length > 0 ? formatTimestamp(state.logs[0].created_at) : "No events";
  systemOnlinePill.textContent = state.system;
  systemOnlinePill.className = `status-pill ${state.system === "online" ? "status-connected" : "status-disconnected"}`;
  socketBadge.textContent = state.wsOnline ? "WS online" : "WS offline";
  socketBadge.className = `socket-badge ${state.wsOnline ? "online" : "offline"}`;
}

function renderReaders() {
  if (state.readers.length === 0) {
    readersGrid.innerHTML = '<div class="empty-state">No readers configured.</div>';
    return;
  }

  readersGrid.innerHTML = state.readers
    .map((reader) => {
      const lastError = reader.last_error
        ? `<div><span class="reader-meta-label">Last error</span><div class="reader-meta-value">${escapeHtml(reader.last_error)}</div></div>`
        : "";
      const ledInfo = reader.led_enabled
        ? `<div>
              <span class="reader-meta-label">Status LED</span>
              <div class="reader-meta-value">GPIO ${escapeHtml(reader.led_gpio_pin)} · ${reader.led_active_high ? "active-high" : "active-low"}</div>
            </div>`
        : `<div>
              <span class="reader-meta-label">Status LED</span>
              <div class="reader-meta-value">Not configured</div>
            </div>`;

      return `
        <article class="reader-card">
          <div class="reader-header">
            <div>
              <h3 class="reader-title">${escapeHtml(reader.name)}</h3>
              <p class="reader-subtitle">${escapeHtml(reader.id)} · ${escapeHtml(reader.type.toUpperCase())} · ${escapeHtml(reader.interface.toUpperCase())}</p>
            </div>
            <div class="badge-stack">
              <span class="reader-badge ${statusClass(reader.status)}">${escapeHtml(reader.status)}</span>
              <span class="reader-badge mode-${escapeHtml(reader.mode)}">${escapeHtml(reader.mode)}</span>
            </div>
          </div>
          <div class="reader-grid">
            <div>
              <span class="reader-meta-label">Last UID</span>
              <div class="reader-meta-value">${escapeHtml(reader.last_uid || "No scans yet")}</div>
            </div>
            <div>
              <span class="reader-meta-label">Last seen</span>
              <div class="reader-meta-value">${escapeHtml(formatTimestamp(reader.last_seen))}</div>
            </div>
            <div>
              <span class="reader-meta-label">Enabled</span>
              <div class="reader-meta-value">${reader.enabled ? "Yes" : "No"}</div>
            </div>
            <div>
              <span class="reader-meta-label">Mode</span>
              <div class="reader-meta-value">${escapeHtml(reader.mode)}</div>
            </div>
            ${ledInfo}
            ${lastError}
          </div>
          <div class="reader-actions">
            <button
              class="action-button primary"
              data-reader-action="scan:${escapeHtml(reader.id)}"
              type="button"
            >
              Scan test
            </button>
            <button
              class="action-button secondary"
              data-reader-action="reset:${escapeHtml(reader.id)}"
              type="button"
            >
              Reset
            </button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderLogs() {
  if (state.logs.length === 0) {
    logsList.innerHTML = '<div class="empty-state">No events recorded yet.</div>';
    return;
  }

  logsList.innerHTML = state.logs
    .map(
      (event) => `
        <article class="log-item">
          <div class="log-item-header">
            <div>
              <p class="log-item-title">${escapeHtml(event.event_type)}</p>
              <span class="log-item-meta">${escapeHtml(event.reader_id || "system")}</span>
            </div>
            <span class="log-item-meta">${escapeHtml(formatTimestamp(event.created_at))}</span>
          </div>
          <p class="log-item-copy">${escapeHtml(event.message)}</p>
          ${event.uid ? `<p class="log-item-copy">UID: ${escapeHtml(event.uid)}</p>` : ""}
        </article>
      `,
    )
    .join("");
}

function render() {
  renderSystem();
  renderReaders();
  renderLogs();
}

function applyStatusPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return;
  }
  state.system = payload.system || state.system;
  state.readers = Array.isArray(payload.readers) ? payload.readers : state.readers;
  render();
}

function applyLogsPayload(payload) {
  if (Array.isArray(payload.logs)) {
    state.logs = payload.logs;
  } else if (payload.event) {
    state.logs = [payload.event, ...state.logs].slice(0, 100);
  }
  render();
}

function connectSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    return;
  }

  socket = new WebSocket(wsUrl());
  socket.onopen = () => {
    state.wsOnline = true;
    render();
  };
  socket.onmessage = (message) => {
    const payload = JSON.parse(message.data);
    if (payload.type === "status_update") {
      applyStatusPayload(payload.data);
      return;
    }
    if (payload.type === "logs_updated") {
      applyLogsPayload(payload);
      return;
    }
    if (payload.type === "reader_connected" || payload.type === "reader_disconnected" || payload.type === "error") {
      loadInitialData().catch((error) => console.error(error));
      return;
    }
    if (payload.type === "card_detected") {
      loadInitialData().catch((error) => console.error(error));
    }
  };
  socket.onclose = () => {
    state.wsOnline = false;
    render();
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
    }
    reconnectTimer = window.setTimeout(connectSocket, 1500);
  };
  socket.onerror = () => {
    state.wsOnline = false;
    render();
  };
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const action = target.dataset.readerAction;
  if (!action) {
    return;
  }
  const [kind, readerId] = action.split(":");
  runReaderAction(readerId, kind).catch((error) => console.error(error));
});

refreshButton.addEventListener("click", () => {
  loadInitialData().catch((error) => window.alert(`Refresh failed: ${error.message}`));
});

loadInitialData()
  .then(() => connectSocket())
  .catch((error) => {
    console.error(error);
    connectSocket();
  });
