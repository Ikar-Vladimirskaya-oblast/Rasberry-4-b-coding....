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

function formatStatusLabel(status) {
  const labels = {
    online: "Онлайн",
    offline: "Офлайн",
    starting: "Запуск",
    connected: "Подключен",
    disconnected: "Отключен",
    error: "Ошибка",
    scanning: "Сканирование",
  };
  return labels[status] || status || "Неизвестно";
}

function formatModeLabel(mode) {
  const labels = {
    hardware: "Железо",
    mock: "Mock",
  };
  return labels[mode] || mode || "Неизвестно";
}

function formatBoolean(value) {
  return value ? "Да" : "Нет";
}

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
    return "Никогда";
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
  systemState.textContent = formatStatusLabel(state.system);
  readerCount.textContent = String(state.readers.length);
  lastEventTime.textContent = state.logs.length > 0 ? formatTimestamp(state.logs[0].created_at) : "Нет событий";
  systemOnlinePill.textContent = formatStatusLabel(state.system);
  systemOnlinePill.className = `status-pill ${state.system === "online" ? "status-connected" : "status-disconnected"}`;
  socketBadge.textContent = state.wsOnline ? "WS online" : "WS offline";
  socketBadge.className = `socket-badge ${state.wsOnline ? "online" : "offline"}`;
}

function renderReaders() {
  if (state.readers.length === 0) {
    readersGrid.innerHTML = '<div class="empty-state">Ридеры не настроены.</div>';
    return;
  }

  readersGrid.innerHTML = state.readers
    .map((reader) => {
      const lastError = reader.last_error
        ? `<div><span class="reader-meta-label">Последняя ошибка</span><div class="reader-meta-value">${escapeHtml(reader.last_error)}</div></div>`
        : "";
      const ledInfo = reader.led_enabled
        ? `<div>
              <span class="reader-meta-label">Светодиод</span>
              <div class="reader-meta-value">${escapeHtml(reader.led_mode)} · GPIO ${escapeHtml(reader.led_gpio_pin)} · pixel ${escapeHtml(reader.led_pixel_index + 1)}/${escapeHtml(reader.led_pixel_count)} · brightness ${escapeHtml(reader.led_brightness)}</div>
            </div>`
        : `<div>
              <span class="reader-meta-label">Светодиод</span>
              <div class="reader-meta-value">Не настроен</div>
            </div>`;

      return `
        <article class="reader-card">
          <div class="reader-header">
            <div>
              <h3 class="reader-title">${escapeHtml(reader.name)}</h3>
              <p class="reader-subtitle">${escapeHtml(reader.id)} · ${escapeHtml(reader.type.toUpperCase())} · ${escapeHtml(reader.interface.toUpperCase())}</p>
            </div>
            <div class="badge-stack">
              <span class="reader-badge ${statusClass(reader.status)}">${escapeHtml(formatStatusLabel(reader.status))}</span>
              <span class="reader-badge mode-${escapeHtml(reader.mode)}">${escapeHtml(formatModeLabel(reader.mode))}</span>
            </div>
          </div>
          <div class="reader-grid">
            <div>
              <span class="reader-meta-label">Последний UID</span>
              <div class="reader-meta-value">${escapeHtml(reader.last_uid || "Сканов пока не было")}</div>
            </div>
            <div>
              <span class="reader-meta-label">Последнее чтение</span>
              <div class="reader-meta-value">${escapeHtml(formatTimestamp(reader.last_seen))}</div>
            </div>
            <div>
              <span class="reader-meta-label">Включен</span>
              <div class="reader-meta-value">${formatBoolean(reader.enabled)}</div>
            </div>
            <div>
              <span class="reader-meta-label">Режим</span>
              <div class="reader-meta-value">${escapeHtml(formatModeLabel(reader.mode))}</div>
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
              Тест скан
            </button>
            <button
              class="action-button secondary"
              data-reader-action="reset:${escapeHtml(reader.id)}"
              type="button"
            >
              Сброс
            </button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderLogs() {
  if (state.logs.length === 0) {
    logsList.innerHTML = '<div class="empty-state">Событий пока нет.</div>';
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
  loadInitialData().catch((error) => window.alert(`Не удалось обновить данные: ${error.message}`));
});

loadInitialData()
  .then(() => connectSocket())
  .catch((error) => {
    console.error(error);
    connectSocket();
  });
