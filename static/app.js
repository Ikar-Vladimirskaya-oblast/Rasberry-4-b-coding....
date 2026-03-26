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
const connectedReaderCount = document.getElementById("connectedReaderCount");
const lastEventTime = document.getElementById("lastEventTime");
const socketBadge = document.getElementById("socketBadge");
const systemOnlinePill = document.getElementById("systemOnlinePill");
const readerSlotCount = document.getElementById("readerSlotCount");
const readerOnlineCount = document.getElementById("readerOnlineCount");
const readerPendingCount = document.getElementById("readerPendingCount");

const desiredReaderSlots = Math.max(1, Number.parseInt(document.body.dataset.readerSlots || "6", 10) || 6);

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

function targetReaderSlots() {
  return Math.max(desiredReaderSlots, state.readers.length);
}

function countOnlineReaders() {
  return state.readers.filter((reader) => ["connected", "scanning"].includes(reader.status)).length;
}

function detectReaderSlot(reader, fallbackIndex) {
  const candidates = [reader.id, reader.name];
  for (const candidate of candidates) {
    const match = String(candidate || "").match(/(\d+)(?!.*\d)/);
    if (!match) {
      continue;
    }
    const slot = Number.parseInt(match[1], 10);
    if (Number.isInteger(slot) && slot > 0) {
      return slot;
    }
  }
  return fallbackIndex + 1;
}

function buildReaderSlots() {
  const slots = Array.from({ length: targetReaderSlots() }, (_, index) => ({
    slot: index + 1,
    reader: null,
  }));

  const orderedReaders = [...state.readers].sort(
    (left, right) => detectReaderSlot(left, 0) - detectReaderSlot(right, 0),
  );

  orderedReaders.forEach((reader, index) => {
    let slotIndex = detectReaderSlot(reader, index) - 1;
    while (slotIndex < slots.length && slots[slotIndex].reader !== null) {
      slotIndex += 1;
    }
    if (slotIndex >= slots.length) {
      slots.push({ slot: slots.length + 1, reader });
      return;
    }
    slots[slotIndex].reader = reader;
  });

  return slots;
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
  const slotCount = targetReaderSlots();
  const onlineCount = countOnlineReaders();
  systemState.textContent = formatStatusLabel(state.system);
  readerCount.textContent = `${state.readers.length} / ${slotCount}`;
  connectedReaderCount.textContent = String(onlineCount);
  lastEventTime.textContent = state.logs.length > 0 ? formatTimestamp(state.logs[0].created_at) : "Нет событий";
  systemOnlinePill.textContent = formatStatusLabel(state.system);
  systemOnlinePill.className = `status-pill ${state.system === "online" ? "status-connected" : "status-disconnected"}`;
  socketBadge.textContent = state.wsOnline ? "WS online" : "WS offline";
  socketBadge.className = `socket-badge ${state.wsOnline ? "online" : "offline"}`;
  readerSlotCount.textContent = String(slotCount);
  readerOnlineCount.textContent = String(onlineCount);
  readerPendingCount.textContent = String(Math.max(slotCount - state.readers.length, 0));
}

function renderReaders() {
  readersGrid.innerHTML = buildReaderSlots()
    .map(({ slot, reader }) => {
      if (!reader) {
        return `
          <article class="reader-card reader-card--placeholder">
            <div class="reader-header">
              <div>
                <h3 class="reader-title">Слот ${slot}</h3>
                <p class="reader-subtitle">Ридер ещё не настроен в backend</p>
              </div>
              <div class="badge-stack">
                <span class="reader-badge status-disconnected">Ожидание</span>
              </div>
            </div>
            <div class="reader-grid">
              <div>
                <span class="reader-meta-label">Назначение</span>
                <div class="reader-meta-value">Ридер через мультиплексор</div>
              </div>
              <div>
                <span class="reader-meta-label">Статус</span>
                <div class="reader-meta-value">Нет данных</div>
              </div>
              <div>
                <span class="reader-meta-label">Последний UID</span>
                <div class="reader-meta-value">Нет чтения</div>
              </div>
              <div>
                <span class="reader-meta-label">Последнее чтение</span>
                <div class="reader-meta-value">Никогда</div>
              </div>
            </div>
          </article>
        `;
      }

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
              <div class="reader-slot">Слот ${slot}</div>
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
