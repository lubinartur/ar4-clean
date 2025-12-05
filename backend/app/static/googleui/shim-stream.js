// AIR4 shim: перехват /chat → /chat/stream с поддержкой session_id
(() => {
  if (typeof window === "undefined" || !window.fetch) return;
  const ORIG_FETCH = window.fetch;

  function tidy(s) {
    return s
      .replace(/\s+/g, " ")
      .replace(/\s([,.!?;:])/g, "$1")
      .trim();
  }

  async function streamToReply(text, sessionId) {
    const payload = sessionId ? { text, session_id: sessionId } : { text };

    const res = await ORIG_FETCH("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.body) return "";

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let full = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });

      let cut;
      while ((cut = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, cut);
        buf = buf.slice(cut + 2);

        if (frame.startsWith("data:")) {
          let payload = frame.slice(5);
          if (payload.startsWith(" ")) payload = payload.slice(1);
          if (payload === "[DONE]") {
            buf = "";
            break;
          }
          if (!payload.startsWith("[error]") && payload !== "") {
            full += payload;
          }
        }
      }
    }
    return tidy(full);
  }

  window.fetch = async (url, opts = {}) => {
    try {
      const method = (opts.method || "GET").toUpperCase();
      const isChat =
        typeof url === "string" && url.includes("/chat") && method === "POST";
      const isSend3 =
        typeof url === "string" && url.includes("/send3") && method === "POST";

      if (isChat || isSend3) {
        let bodyObj = {};
        try {
          bodyObj = JSON.parse(opts.body || "{}");
        } catch {
          bodyObj = {};
        }

        const text =
          bodyObj.text ||
          bodyObj.q ||
          bodyObj.prompt ||
          bodyObj.message ||
          (Array.isArray(bodyObj.messages) &&
            bodyObj.messages.length > 0 &&
            typeof bodyObj.messages[bodyObj.messages.length - 1].content ===
              "string" &&
            bodyObj.messages[bodyObj.messages.length - 1].content) ||
          "";

        const sessionId =
          (typeof window !== "undefined" && window.air4CurrentSessionId) ||
          "ui";

        if (typeof text === "string" && text.trim()) {
          streamToReply(text, sessionId)
            .then((reply) => {
              if (typeof window !== "undefined") {
                window.air4LastReply = reply || "";
                if (typeof window.air4PatchNoResponseBubbles === "function") {
                  window.air4PatchNoResponseBubbles();
                }
              }
            })
            .catch(() => {});
        }
      }
    } catch {
      // fall back
    }
    return ORIG_FETCH(url, opts);
  };
})();

// AIR4: SSE status banner + EventSource wrapper
(function () {
  if (typeof window === "undefined" || !window.EventSource) return;

  const NativeEventSource = window.EventSource;

  function ensureAir4Banner() {
    let bar = document.getElementById("air4-stream-status");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "air4-stream-status";
      bar.textContent = "⚠️ Ошибка соединения с AIR4. Переподключаюсь…";
      bar.style.position = "fixed";
      bar.style.top = "0";
      bar.style.left = "0";
      bar.style.right = "0";
      bar.style.zIndex = "9999";
      bar.style.padding = "6px 12px";
      bar.style.fontSize = "13px";
      bar.style.fontFamily =
        "system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
      bar.style.textAlign = "center";
      bar.style.background = "#b91c1c";
      bar.style.color = "#fff";
      bar.style.display = "none";

      document.addEventListener("DOMContentLoaded", function () {
        if (!document.body.contains(bar)) {
          document.body.appendChild(bar);
        }
      });

      if (document.body && !document.body.contains(bar)) {
        document.body.appendChild(bar);
      }
    }
    return bar;
  }

  function showAir4Banner() {
    const bar = ensureAir4Banner();
    if (bar) bar.style.display = "block";
  }

  function hideAir4Banner() {
    const bar = document.getElementById("air4-stream-status");
    if (bar) bar.style.display = "none";
  }

  function Air4EventSource(url, config) {
    const es = new NativeEventSource(url, config);

    es.addEventListener("open", function () {
      hideAir4Banner();
    });

    es.addEventListener("error", function () {
      showAir4Banner();
    });

    return es;
  }

  Air4EventSource.prototype = NativeEventSource.prototype;
  window.EventSource = Air4EventSource;
})();

// AIR4: убрать приветственный бабл "Привет! Как дела?"
(function () {
  if (typeof window === "undefined") return;

  function removeGreetingBubble() {
    const needle = "Привет! Как дела?";
    let removed = false;

    const allDivs = document.querySelectorAll("div");
    allDivs.forEach((el) => {
      if (removed) return;
      const text = (el.textContent || "").trim();
      if (!text.startsWith(needle)) return;

      let target = el;
      for (let i = 0; i < 3 && target && target.parentElement; i++) {
        if (target.parentElement.childElementCount > 1) {
          target = target.parentElement;
          break;
        }
        target = target.parentElement;
      }
      if (target && target.parentElement) {
        target.parentElement.removeChild(target);
        removed = true;
      }
    });
    return removed;
  }

  function setupObserver() {
    if (removeGreetingBubble()) return;

    const obs = new MutationObserver(() => {
      if (removeGreetingBubble()) {
        obs.disconnect();
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupObserver);
  } else {
    setupObserver();
  }
})();

// AIR4: заменить [No response payload] на последний ответ
(function () {
  if (typeof window === "undefined") return;

  function patchBubbles(root) {
    const reply = (window.air4LastReply || "").trim();
    if (!reply) return;

    const scope = root && root.querySelectorAll ? root : document;
    const nodes = scope.querySelectorAll("div");
    nodes.forEach((el) => {
      const txt = (el.textContent || "").trim();
      if (txt === "[No response payload]") {
        el.textContent = reply;
      }
    });
  }

  window.air4PatchNoResponseBubbles = function () {
    if (!document.body) return;
    patchBubbles(document.body);
  };

  function setupObserver() {
    if (!document.body) return;
    patchBubbles(document.body);
    const obs = new MutationObserver((mutList) => {
      mutList.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.nodeType === 1) {
            patchBubbles(node);
          }
        });
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupObserver);
  } else {
    setupObserver();
  }
})();

// AIR4: История + Настройки + выбор сессии
(function () {
  if (typeof window === "undefined" || !window.fetch) return;

  // --- глобальное состояние текущей сессии ---
  let currentSessionId = "ui";
  try {
    const stored =
      typeof window !== "undefined" &&
      window.localStorage &&
      window.localStorage.getItem("air4.currentSessionId");
    if (stored) currentSessionId = stored;
  } catch {}
  if (typeof window !== "undefined") {
    window.air4CurrentSessionId = currentSessionId;
  }

  function setCurrentSessionId(id) {
    currentSessionId = id || "ui";
    if (typeof window !== "undefined") {
      window.air4CurrentSessionId = currentSessionId;
      try {
        window.localStorage.setItem("air4.currentSessionId", currentSessionId);
      } catch {}
    }
    const title = document.getElementById("air4-sessions-title");
    if (title) {
      title.textContent = `AIR4 • История (${currentSessionId})`;
    }
  }

  // --- загрузка списка сессий в селектор ---
  async function loadSessionsList(selectEl) {
    try {
      const res = await fetch("/sessions");
      if (!res.ok) {
        return;
      }
      const js = await res.json();
      const sessions = js.sessions || [];
      selectEl.innerHTML = "";

      if (!sessions.length) {
        const opt = document.createElement("option");
        opt.value = currentSessionId;
        opt.textContent = currentSessionId;
        selectEl.appendChild(opt);
        setCurrentSessionId(currentSessionId);
        return;
      }

      sessions.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.id;
        selectEl.appendChild(opt);
      });

      const hasCurrent = sessions.some((s) => s.id === currentSessionId);
      if (!hasCurrent) {
        currentSessionId = sessions[0].id;
        if (typeof window !== "undefined") {
          window.air4CurrentSessionId = currentSessionId;
        }
      }
      selectEl.value = currentSessionId;
      setCurrentSessionId(currentSessionId);
    } catch {
      // ignore
    }
  }

  // --- История ---
  function createHistoryUI() {
    if (document.getElementById("air4-history-btn")) return;

    const btn = document.createElement("button");
    btn.id = "air4-history-btn";
    btn.textContent = "История";
    btn.style.position = "fixed";
    btn.style.bottom = "16px";
    btn.style.left = "16px";
    btn.style.zIndex = "9999";
    btn.style.padding = "6px 10px";
    btn.style.fontSize = "12px";
    btn.style.fontFamily =
      "system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
    btn.style.borderRadius = "999px";
    btn.style.border = "none";
    btn.style.cursor = "pointer";
    btn.style.background = "#111827";
    btn.style.color = "#f9fafb";
    btn.style.opacity = "0.8";
    btn.style.boxShadow = "0 2px 6px rgba(0,0,0,0.3)";
    btn.onmouseenter = () => (btn.style.opacity = "1");
    btn.onmouseleave = () => (btn.style.opacity = "0.8");

    const panel = document.createElement("div");
    panel.id = "air4-sessions-panel";
    panel.style.position = "fixed";
    panel.style.right = "16px";
    panel.style.bottom = "16px";
    panel.style.width = "360px";
    panel.style.maxHeight = "60vh";
    panel.style.zIndex = "9998";
    panel.style.padding = "10px";
    panel.style.borderRadius = "12px";
    panel.style.background = "rgba(17,24,39,0.96)";
    panel.style.color = "#e5e7eb";
    panel.style.fontSize = "12px";
    panel.style.fontFamily =
      "system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
    panel.style.boxShadow = "0 4px 24px rgba(0,0,0,0.5)";
    panel.style.overflow = "auto";
    panel.style.display = "none";

    // верхняя строка: заголовок + селектор
    const headerRow = document.createElement("div");
    headerRow.style.display = "flex";
    headerRow.style.alignItems = "center";
    headerRow.style.justifyContent = "space-between";
    headerRow.style.marginBottom = "6px";
    headerRow.style.gap = "8px";

    const title = document.createElement("div");
    title.id = "air4-sessions-title";
    title.textContent = `AIR4 • История (${currentSessionId})`;
    title.style.fontWeight = "600";

    const selectSess = document.createElement("select");
    selectSess.id = "air4-sessions-select";
    selectSess.style.flex = "0 0 140px";
    selectSess.style.fontSize = "12px";
    selectSess.style.padding = "2px 4px";
    selectSess.style.borderRadius = "6px";
    selectSess.style.border = "1px solid #374151";
    selectSess.style.background = "#111827";
    selectSess.style.color = "#e5e7eb";

    headerRow.appendChild(title);
    headerRow.appendChild(selectSess);

    // вторая строка: кнопки
    const buttonsRow = document.createElement("div");
    buttonsRow.style.display = "flex";
    buttonsRow.style.alignItems = "center";
    buttonsRow.style.gap = "6px";
    buttonsRow.style.marginBottom = "6px";

    const reload = document.createElement("button");
    reload.textContent = "Обновить";
    reload.style.fontSize = "11px";
    reload.style.padding = "2px 6px";
    reload.style.borderRadius = "999px";
    reload.style.border = "none";
    reload.style.cursor = "pointer";
    reload.style.background = "#374151";
    reload.style.color = "#e5e7eb";

    const clearBtn = document.createElement("button");
    clearBtn.textContent = "Очистить";
    clearBtn.style.fontSize = "11px";
    clearBtn.style.padding = "2px 8px";
    clearBtn.style.borderRadius = "999px";
    clearBtn.style.border = "none";
    clearBtn.style.cursor = "pointer";
    clearBtn.style.background = "#b91c1c";
    clearBtn.style.color = "#f9fafb";

    const newBtn = document.createElement("button");
    newBtn.textContent = "+ Новый чат";
    newBtn.style.fontSize = "11px";
    newBtn.style.padding = "2px 8px";
    newBtn.style.borderRadius = "999px";
    newBtn.style.border = "none";
    newBtn.style.cursor = "pointer";
    newBtn.style.background = "#2563eb";
    newBtn.style.color = "#f9fafb";

    buttonsRow.appendChild(reload);
    buttonsRow.appendChild(clearBtn);
    buttonsRow.appendChild(newBtn);

    const body = document.createElement("div");
    body.id = "air4-sessions-body";
    body.textContent = "Загрузка…";

    panel.appendChild(headerRow);
    panel.appendChild(buttonsRow);
    panel.appendChild(body);

    // поведение
    btn.onclick = () => {
      panel.style.display = panel.style.display === "none" ? "block" : "none";
      if (panel.style.display === "block") {
        loadSessionsList(selectSess);
        loadHistory(currentSessionId, body);
      }
    };

    selectSess.onchange = () => {
      const sid = selectSess.value || "ui";
      setCurrentSessionId(sid);
      loadHistory(currentSessionId, body);
    };

    reload.onclick = () => {
      loadSessionsList(selectSess);
      loadHistory(currentSessionId, body);
    };

    clearBtn.onclick = async () => {
      try {
        const res = await fetch(
          `/sessions/${encodeURIComponent(currentSessionId)}/clear`,
          { method: "POST" }
        );
        if (!res.ok) {
          body.textContent = "Ошибка при очистке истории";
          return;
        }
        body.textContent = "История очищена.";
      } catch (e) {
        body.textContent = "Ошибка: " + e;
      }
    };

    newBtn.onclick = async () => {
      const ts = Date.now();
      const rand = Math.random().toString(36).slice(2, 6);
      const sid = `chat-${ts}-${rand}`;
      setCurrentSessionId(sid);
      await loadSessionsList(selectSess);
      selectSess.value = sid;
      body.textContent = "Новый чат. Сообщений пока нет.";
    };

    document.body.appendChild(btn);
    document.body.appendChild(panel);
  }

  async function loadHistory(sessionId, bodyEl) {
    try {
      bodyEl.textContent = "Загрузка...";
      const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`);
      if (!res.ok) {
        bodyEl.textContent = "Ошибка загрузки истории";
        return;
      }
      const js = await res.json();
      const msgs = js.messages || [];
      if (!msgs.length) {
        bodyEl.textContent = "Сообщений пока нет.";
        return;
      }
      const frag = document.createDocumentFragment();
      msgs.slice(-30).forEach((m) => {
        const row = document.createElement("div");
        row.style.marginBottom = "6px";
        const role = document.createElement("div");
        role.textContent = m.role === "user" ? "Ты:" : "AIR4:";
        role.style.fontWeight = "600";
        const txt = document.createElement("div");
        txt.textContent = m.content;
        txt.style.whiteSpace = "pre-wrap";
        txt.style.fontSize = "11px";
        frag.appendChild(role);
        frag.appendChild(txt);
      });
      bodyEl.innerHTML = "";
      bodyEl.appendChild(frag);
    } catch (e) {
      bodyEl.textContent = "Ошибка: " + e;
    }
  }

  // --- Настройки профиля ---
  function createSettingsUI() {
    if (document.getElementById("air4-settings-btn")) return;

    const btn = document.createElement("button");
    btn.id = "air4-settings-btn";
    btn.textContent = "⚙ Настройки";
    btn.style.position = "fixed";
    btn.style.bottom = "56px";
    btn.style.left = "16px";
    btn.style.zIndex = "9999";
    btn.style.padding = "6px 10px";
    btn.style.fontSize = "12px";
    btn.style.fontFamily =
      "system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
    btn.style.borderRadius = "999px";
    btn.style.border = "none";
    btn.style.cursor = "pointer";
    btn.style.background = "#111827";
    btn.style.color = "#f9fafb";
    btn.style.opacity = "0.8";
    btn.style.boxShadow = "0 2px 6px rgba(0,0,0,0.3)";
    btn.onmouseenter = () => (btn.style.opacity = "1");
    btn.onmouseleave = () => (btn.style.opacity = "0.8");

    const panel = document.createElement("div");
    panel.id = "air4-settings-panel";
    panel.style.position = "fixed";
    panel.style.right = "16px";
    panel.style.bottom = "16px";
    panel.style.width = "280px";
    panel.style.zIndex = "9998";
    panel.style.padding = "10px";
    panel.style.borderRadius = "12px";
    panel.style.background = "rgba(17,24,39,0.96)";
    panel.style.color = "#e5e7eb";
    panel.style.fontSize = "12px";
    panel.style.fontFamily =
      "system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
    panel.style.boxShadow = "0 4px 24px rgba(0,0,0,0.5)";
    panel.style.display = "none";

    const title = document.createElement("div");
    title.textContent = "AIR4 • Настройки ответа";
    title.style.fontWeight = "600";
    title.style.marginBottom = "6px";

    const form = document.createElement("form");

    const rowStyle = document.createElement("div");
    rowStyle.style.marginBottom = "6px";
    const labelStyle = document.createElement("label");
    labelStyle.textContent = "Стиль ответа:";
    labelStyle.style.display = "block";
    labelStyle.style.marginBottom = "2px";

    const selectStyle = document.createElement("select");
    selectStyle.style.width = "100%";
    selectStyle.style.fontSize = "12px";
    selectStyle.style.padding = "2px 4px";
    selectStyle.style.borderRadius = "6px";
    selectStyle.style.border = "1px solid #374151";
    selectStyle.style.background = "#111827";
    selectStyle.style.color = "#e5e7eb";

    [
      ["short", "Кратко"],
      ["normal", "Нормально"],
      ["detailed", "Подробно"],
    ].forEach(([val, label]) => {
      const opt = document.createElement("option");
      opt.value = val;
      opt.textContent = label;
      selectStyle.appendChild(opt);
    });

    rowStyle.appendChild(labelStyle);
    rowStyle.appendChild(selectStyle);

    const rowLang = document.createElement("div");
    rowLang.style.marginBottom = "6px";
    const labelLang = document.createElement("label");
    labelLang.textContent = "Язык:";
    labelLang.style.display = "block";
    labelLang.style.marginBottom = "2px";

    const selectLang = document.createElement("select");
    selectLang.style.width = "100%";
    selectLang.style.fontSize = "12px";
    selectLang.style.padding = "2px 4px";
    selectLang.style.borderRadius = "6px";
    selectLang.style.border = "1px solid #374151";
    selectLang.style.background = "#111827";
    selectLang.style.color = "#e5e7eb";

    [
      ["ru", "Русский"],
      ["en", "English"],
      ["auto", "Auto"],
    ].forEach(([val, label]) => {
      const opt = document.createElement("option");
      opt.value = val;
      opt.textContent = label;
      selectLang.appendChild(opt);
    });

    rowLang.appendChild(labelLang);
    rowLang.appendChild(selectLang);

    const saveBtn = document.createElement("button");
    saveBtn.type = "submit";
    saveBtn.textContent = "Сохранить";
    saveBtn.style.marginTop = "4px";
    saveBtn.style.fontSize = "12px";
    saveBtn.style.padding = "4px 10px";
    saveBtn.style.borderRadius = "999px";
    saveBtn.style.border = "none";
    saveBtn.style.cursor = "pointer";
    saveBtn.style.background = "#2563eb";
    saveBtn.style.color = "#f9fafb";

    const status = document.createElement("div");
    status.style.marginTop = "4px";
    status.style.fontSize = "11px";
    status.style.opacity = "0.8";

    form.appendChild(rowStyle);
    form.appendChild(rowLang);
    form.appendChild(saveBtn);
    form.appendChild(status);

    panel.appendChild(title);
    panel.appendChild(form);

    btn.onclick = () => {
      panel.style.display = panel.style.display === "none" ? "block" : "none";
      if (panel.style.display === "block") {
        loadSettings(selectStyle, selectLang, status);
      }
    };

    form.onsubmit = (e) => {
      e.preventDefault();
      saveSettings(selectStyle.value, selectLang.value, status);
    };

    document.body.appendChild(btn);
    document.body.appendChild(panel);
  }

  async function loadSettings(selectStyle, selectLang, statusEl) {
    try {
      statusEl.textContent = "Загружаю профиль…";
      const res = await fetch("/memory/profile");
      if (!res.ok) {
        statusEl.textContent = "Ошибка загрузки профиля";
        return;
      }
      const js = await res.json();
      const prefs = js.preferences || {};
      if (prefs.reply_style) {
        selectStyle.value = prefs.reply_style;
      }
      if (prefs.language) {
        selectLang.value = prefs.language;
      }
      statusEl.textContent = "Профиль загружен";
    } catch (e) {
      statusEl.textContent = "Ошибка: " + e;
    }
  }

  async function saveSettings(replyStyle, language, statusEl) {
    try {
      statusEl.textContent = "Сохраняю…";
      const res = await fetch("/memory/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferences: {
            reply_style: replyStyle,
            language: language,
          },
        }),
      });
      if (!res.ok) {
        statusEl.textContent = "Ошибка сохранения";
        return;
      }
      statusEl.textContent = "Сохранено ✓";
    } catch (e) {
      statusEl.textContent = "Ошибка: " + e;
    }
  }

  function boot() {
    createHistoryUI();
    createSettingsUI();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

