const state = {
  data: null,
  activeTab: "dashboard",
  search: "",
  itemSearch: "",
  previousSlots: new Map(),
  dismissedUnknown: new Set(),
};

const statusClass = {
  empty: "empty",
  ok: "ok",
  unknown: "unknown",
  wrong: "wrong",
  error: "error",
};

const slotDisplayOrder = [2, 3, 1, 4];
const stateRefreshMs = 500;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Ошибка запроса");
  }
  return data;
}

function text(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : value;
}

function haystack(values) {
  return values.filter(Boolean).join(" ").toLowerCase();
}

function slotMatches(slot, query) {
  if (!query) return true;
  return haystack([
    slot.name,
    `слот ${slot.slot_number}`,
    `ячейка ${slot.slot_number}`,
    slot.current_uid,
    slot.current_item_name,
    slot.expected_item_name,
    slot.status_label,
  ]).includes(query);
}

function itemMatches(item, query) {
  if (!query) return true;
  return haystack([
    item.name,
    item.uid,
    item.note,
    `слот ${item.slot_number}`,
    `ячейка ${item.slot_number}`,
  ]).includes(query);
}

function renderSystem() {
  const pill = document.getElementById("systemPill");
  const runtime = state.data?.runtime || {};
  const running = runtime.running && runtime.hardware_ready;
  const bad = runtime.running && !runtime.hardware_ready;
  pill.innerHTML = `
    <span class="dot ${running ? "dot-ok" : bad ? "dot-bad" : "dot-warn"}"></span>
    <span>${running ? "Онлайн" : bad ? "Ошибка" : "Ожидание"}</span>
  `;
}

function renderOverview() {
  const grid = document.getElementById("overviewGrid");
  const slots = state.data?.slots || [];
  const readers = state.data?.runtime?.readers || {};
  const items = state.data?.items || [];
  const onlineReaders = Object.values(readers).filter((reader) => reader.online).length;
  const occupied = slots.filter((slot) => slot.current_uid).length;
  const okSlots = slots.filter((slot) => slot.status === "ok").length;
  const unknownSlots = slots.filter((slot) => slot.status === "unknown" || slot.status === "wrong").length;
  const ledMode = "по запросу";
  const cloud = state.data?.cloud || {};
  const cloudMode = cloud.connected ? "онлайн" : cloud.enabled ? "офлайн" : "выкл";
  const cloudText = cloud.connected
    ? (cloud.last_sync ? `синк ${cloud.last_sync}` : "соединение есть")
    : (cloud.last_error || "локальная SQLite");

  grid.innerHTML = `
    <article class="metric-card">
      <span>Ридеры</span>
      <strong>${onlineReaders}/4</strong>
      <em>PN532 online</em>
    </article>
    <article class="metric-card">
      <span>Ячейки</span>
      <strong>${occupied}/4</strong>
      <em>заняты сейчас</em>
    </article>
    <article class="metric-card">
      <span>Совпали</span>
      <strong>${okSlots}</strong>
      <em>${unknownSlots ? `требуют внимания: ${unknownSlots}` : "ошибок нет"}</em>
    </article>
    <article class="metric-card">
      <span>LED</span>
      <strong>${ledMode}</strong>
      <em>синий: свободные · зелёный: найти</em>
    </article>
    <article class="metric-card">
      <span>Cloud</span>
      <strong>${cloudMode}</strong>
      <em>${cloudText}</em>
    </article>
    <article class="metric-card metric-card--wide">
      <span>Последняя метка</span>
      <strong class="uid">${state.data?.runtime?.last_uid || "—"}</strong>
      <em>${items.length} предметов в базе</em>
    </article>
  `;
}

function renderUnknownPrompt(slots) {
  const prompt = document.getElementById("unknownPrompt");
  const unknown = slots.find((slot) => {
    const key = `${slot.slot_number}:${slot.current_uid}`;
    return slot.status === "unknown" && slot.current_uid && !state.dismissedUnknown.has(key);
  });

  if (!unknown) {
    prompt.classList.add("hidden");
    prompt.innerHTML = "";
    return;
  }

  prompt.classList.remove("hidden");
  prompt.innerHTML = `
    <div>
      <strong>Вы что-то положили в ячейку ${unknown.slot_number}?</strong>
      <span class="uid">${unknown.current_uid}</span>
    </div>
    <div class="prompt-actions">
      <button class="primary-button" data-name-unknown="${unknown.slot_number}" data-uid="${unknown.current_uid}">Назвать</button>
      <button class="compact-button" data-dismiss-unknown="${unknown.slot_number}" data-uid="${unknown.current_uid}">Не сейчас</button>
    </div>
  `;
}

function renderDashboard() {
  const grid = document.getElementById("slotsGrid");
  const slots = state.data?.slots || [];
  const query = state.search.trim().toLowerCase();
  const visibleSlots = [...slots]
    .sort((a, b) => slotDisplayOrder.indexOf(a.slot_number) - slotDisplayOrder.indexOf(b.slot_number))
    .filter((slot) => slotMatches(slot, query));

  renderUnknownPrompt(slots);

  grid.innerHTML = visibleSlots.map((slot) => {
    const cls = statusClass[slot.status] || "empty";
    const signature = `${slot.status}:${slot.current_uid || ""}:${slot.expected_uid || ""}`;
    const previous = state.previousSlots.get(slot.slot_number);
    const changed = previous !== undefined && previous !== signature;
    state.previousSlots.set(slot.slot_number, signature);
    return `
      <article class="slot-card ${cls} ${changed ? "slot-card--pulse" : ""}" data-slot="${slot.slot_number}">
        <div class="slot-head">
          <div>
            <div class="label">${slot.name}</div>
            <div class="slot-number">${slot.slot_number}</div>
          </div>
          <div class="status-badge">${text(slot.status_label)}</div>
        </div>
        <div class="slot-body">
          <div>
            <div class="label">Назначено</div>
            <div class="value">${text(slot.expected_item_name, "Нет предмета")}</div>
          </div>
          <div>
            <div class="label">Сейчас</div>
            <div class="value">${text(slot.current_item_name, slot.current_uid ? "Метка без предмета" : "Пусто")}</div>
          </div>
          <div>
            <div class="label">UID</div>
            <div class="value uid">${text(slot.current_uid)}</div>
          </div>
          ${slot.error ? `<div><div class="label">Событие</div><div class="value">${slot.error}</div></div>` : ""}
        </div>
        <div class="slot-foot">
          <span>TCA ${slot.tca_channel}</span>
          <span>LED ${slot.led_number}</span>
        </div>
      </article>
    `;
  }).join("") || `<div class="empty-state">Поиск ничего не нашёл</div>`;
}

function renderItems() {
  const query = state.itemSearch.trim().toLowerCase();
  const items = (state.data?.items || []).filter((item) => itemMatches(item, query));
  document.getElementById("itemsCount").textContent = `${items.length}`;
  document.getElementById("itemsTable").innerHTML = items.map((item) => `
    <tr>
      <td>Слот ${item.slot_number}</td>
      <td>
        <strong>${item.name}</strong>
        ${item.note ? `<div class="muted">${item.note}</div>` : ""}
      </td>
      <td class="uid">${item.uid}</td>
      <td>
        <div class="row-actions">
          <button class="compact-button find-button" data-find="${item.id}">Найти</button>
          <button class="compact-button" data-edit="${item.id}">Править</button>
          <button class="compact-button danger-button" data-delete="${item.id}">Удалить</button>
        </div>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="4" class="muted">Нет предметов</td></tr>`;
}

function renderEvents(events = state.data?.events || []) {
  document.getElementById("eventsTable").innerHTML = events.map((event) => `
    <tr>
      <td>${event.created_at}</td>
      <td>${event.slot_number ? `Слот ${event.slot_number}` : "—"}</td>
      <td>${event.result}</td>
      <td class="uid">${text(event.uid)}</td>
      <td>${event.message}</td>
    </tr>
  `).join("");
}

function renderSettings() {
  const settings = state.data?.settings || {};
  const runtime = state.data?.runtime || {};
  const cloud = state.data?.cloud || {};
  const deviceOnline = Boolean(cloud.connected);
  const brightness = document.getElementById("brightness");
  if (document.activeElement !== brightness) {
    brightness.value = settings.brightness || "80";
  }
  document.getElementById("ledState").textContent = "подсветка только по кнопкам";
  document.getElementById("deviceState").className = `settings-connection ${deviceOnline ? "settings-connection--on" : "settings-connection--off"}`;
  document.getElementById("deviceState").textContent = `Связь: ${deviceOnline ? "есть" : "нет"}`;
  document.getElementById("readerState").textContent = runtime.message || "";
  document.getElementById("mappingList").innerHTML = (state.data?.slots || []).map((slot) => {
    const reader = runtime.readers?.[String(slot.tca_channel)] || {};
    const online = reader.online ? "онлайн" : "нет связи";
    return `
      <div class="mapping-row">
        <span>Слот ${slot.slot_number}</span>
        <span class="muted">TCA ${slot.tca_channel} → LED ${slot.led_number} · ${online}</span>
      </div>
    `;
  }).join("");
}

function renderAll() {
  renderSystem();
  renderOverview();
  renderDashboard();
  renderItems();
  renderEvents();
  renderSettings();
}

async function refreshState() {
  try {
    state.data = await api("/api/state");
    renderAll();
  } catch (error) {
    document.getElementById("systemPill").innerHTML = `<span class="dot dot-bad"></span><span>${error.message}</span>`;
  }
}

function resetItemForm() {
  document.getElementById("itemFormTitle").textContent = "Новый предмет";
  document.getElementById("itemId").value = "";
  document.getElementById("itemName").value = "";
  document.getElementById("itemUid").value = "";
  document.getElementById("itemSlot").value = "1";
  document.getElementById("itemNote").value = "";
  document.getElementById("itemMessage").textContent = "";
}

function editItem(id) {
  const item = (state.data?.items || []).find((entry) => entry.id === id);
  if (!item) return;
  document.getElementById("itemFormTitle").textContent = "Редактировать";
  document.getElementById("itemId").value = item.id;
  document.getElementById("itemName").value = item.name;
  document.getElementById("itemUid").value = item.uid;
  document.getElementById("itemSlot").value = String(item.slot_number);
  document.getElementById("itemNote").value = item.note || "";
  document.querySelector('[data-tab="items"]').click();
}

function nameUnknown(slotNumber, uid) {
  document.getElementById("itemFormTitle").textContent = "Назвать предмет";
  document.getElementById("itemId").value = "";
  document.getElementById("itemName").value = "";
  document.getElementById("itemUid").value = uid;
  document.getElementById("itemSlot").value = String(slotNumber);
  document.getElementById("itemNote").value = "";
  document.getElementById("itemMessage").textContent = "Введите название и сохраните";
  document.querySelector('[data-tab="items"]').click();
  document.getElementById("itemName").focus();
}

async function saveItem(event) {
  event.preventDefault();
  const payload = {
    name: document.getElementById("itemName").value,
    uid: document.getElementById("itemUid").value,
    slot_number: Number(document.getElementById("itemSlot").value),
    note: document.getElementById("itemNote").value,
  };
  const id = document.getElementById("itemId").value;
  const message = document.getElementById("itemMessage");
  try {
    if (id) {
      await api(`/api/items/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/items", { method: "POST", body: JSON.stringify(payload) });
    }
    message.textContent = "Сохранено";
    resetItemForm();
    await refreshState();
  } catch (error) {
    message.textContent = error.message;
  }
}

async function loadHistory() {
  const params = new URLSearchParams();
  const slot = document.getElementById("historySlot").value;
  const query = document.getElementById("historySearch").value.trim();
  if (slot) params.set("slot", slot);
  if (query) params.set("q", query);
  const data = await api(`/api/events?${params.toString()}`);
  renderEvents(data.events);
}

function bindUi() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.tab).classList.add("active");
      state.activeTab = button.dataset.tab;
    });
  });

  document.getElementById("globalSearch").addEventListener("input", (event) => {
    state.search = event.target.value;
    renderDashboard();
  });
  document.getElementById("clearSearch").addEventListener("click", () => {
    state.search = "";
    document.getElementById("globalSearch").value = "";
    renderDashboard();
  });
  document.getElementById("highlightEmpty").addEventListener("click", async () => {
    await api("/api/highlight/empty", { method: "POST", body: "{}" });
    await refreshState();
  });

  document.getElementById("unknownPrompt").addEventListener("click", (event) => {
    const nameSlot = event.target.dataset.nameUnknown;
    const dismissSlot = event.target.dataset.dismissUnknown;
    const uid = event.target.dataset.uid;
    if (nameSlot && uid) {
      nameUnknown(Number(nameSlot), uid);
    }
    if (dismissSlot && uid) {
      state.dismissedUnknown.add(`${dismissSlot}:${uid}`);
      renderDashboard();
    }
  });

  document.getElementById("itemSearch").addEventListener("input", (event) => {
    state.itemSearch = event.target.value;
    renderItems();
  });
  document.getElementById("itemForm").addEventListener("submit", saveItem);
  document.getElementById("resetItemForm").addEventListener("click", resetItemForm);
  document.getElementById("useLastUid").addEventListener("click", () => {
    const latest = state.data?.runtime?.last_uid;
    if (latest) {
      document.getElementById("itemUid").value = latest;
      const latestSlot = state.data?.runtime?.last_uid_slot;
      if (latestSlot) document.getElementById("itemSlot").value = String(latestSlot);
    }
  });

  document.getElementById("itemsTable").addEventListener("click", async (event) => {
    const editId = event.target.dataset.edit;
    const deleteId = event.target.dataset.delete;
    const findId = event.target.dataset.find;
    if (findId) {
      await api(`/api/items/${findId}/highlight`, { method: "POST", body: "{}" });
      await refreshState();
    }
    if (editId) editItem(Number(editId));
    if (deleteId) {
      await api(`/api/items/${deleteId}`, { method: "DELETE" });
      await refreshState();
    }
  });

  document.getElementById("refreshHistory").addEventListener("click", loadHistory);
  document.getElementById("historySlot").addEventListener("change", loadHistory);

  document.getElementById("saveBrightness").addEventListener("click", async () => {
    await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({ brightness: Number(document.getElementById("brightness").value) }),
    });
    await refreshState();
  });
  document.getElementById("ledOff").addEventListener("click", async () => {
    await api("/api/leds/off", { method: "POST", body: "{}" });
    await refreshState();
  });
  document.getElementById("checkHardware").addEventListener("click", async () => {
    await api("/api/hardware/check", { method: "POST", body: "{}" });
    await refreshState();
  });
}

bindUi();
refreshState();
setInterval(refreshState, stateRefreshMs);
