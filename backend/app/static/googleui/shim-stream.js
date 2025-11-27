(() => {
  const ORIG_FETCH = window.fetch;

  const box = document.createElement('div');
  box.id = 'ar4-stream-overlay';
  box.style.cssText = [
    'position:fixed','left:12px','bottom:12px','z-index:99999',
    'max-width:40vw','padding:8px 10px','border-radius:10px',
    'font:12px/1.4 ui-monospace,monospace','color:#cbd5e1',
    'background:rgba(0,0,0,.35)','backdrop-filter:blur(6px)',
    'white-space:pre-wrap','pointer-events:none'
  ].join(';');
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(box));

  function tidy(s) {
    return s
      .replace(/\s+/g, ' ')           // схлопываем длинные пробелы
      .replace(/\s([,.!?;:])/g, '$1') // убираем пробелы перед знаками
      .trim();
  }

  async function streamToReply(text) {
    box.textContent = '';
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!res.body) return '';

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '', full = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });

      let cut;
      while ((cut = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, cut);   // ВАЖНО: без .trim() !
        buf = buf.slice(cut + 2);

        if (frame.startsWith('data:')) {
          let payload = frame.slice(5);    // оставляем ровно то, что прислал сервер
          if (payload.startsWith(' ')) payload = payload.slice(1); // опционально срезаем только один ведущий пробел после "data: "
          if (payload === '[DONE]') { buf = ''; break; }
          if (!payload.startsWith('[error]') && payload !== '') {
            box.textContent += payload; // живой поток как есть
            full += payload;            // буфер для карточки
          }
        }
      }
    }
    return tidy(full);
  }

  window.fetch = async (url, opts = {}) => {
    try {
      const method = (opts.method || 'GET').toUpperCase();
      const isChat  = typeof url === 'string' && url.endsWith('/chat')  && method === 'POST';
      const isSend3 = typeof url === 'string' && url.endsWith('/send3') && method === 'POST';
      if (isChat || isSend3) {
        const body = (() => { try { return JSON.parse(opts.body || '{}'); } catch { return {}; } })();
        const text = body.q || body.text || '';
        if (text) {
          const reply = await streamToReply(text).catch(() => '');
          return new Response(JSON.stringify({ reply }), {
            headers: { 'Content-Type': 'application/json' }
          });
        }
      }
    } catch {}
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
      bar.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
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
