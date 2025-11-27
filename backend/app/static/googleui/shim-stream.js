(()=> {
  const origFetch = window.fetch;
  window.fetch = async (input, init = {}) => {
    try {
      const url = (typeof input === 'string') ? input : input.url;
      const m = (init.method || 'GET').toUpperCase();

      // перехватываем POST /chat с JSON-телом
      const isChat = /\/chat$/.test(url) && m === 'POST' && init.body;
      if (!isChat) return origFetch(input, init);

      let payload = {};
      try { payload = JSON.parse(init.body); } catch {}

      // идём на /chat/stream
      const res = await origFetch(url + '/stream', {
        ...init,
        headers: {'Content-Type':'application/json', ...(init.headers||{})},
        body: JSON.stringify({
          text: payload.text ?? payload.q ?? '',
          session_id: payload.session_id
        })
      });

      // если по какой-то причине нет stream-тела — просто пробуем как JSON
      if (!res.body) {
        const j = await res.json().catch(()=>({reply:''}));
        return new Response(JSON.stringify(j), {headers:{'Content-Type':'application/json'}});
      }

      // парсим text/event-stream и собираем финальный текст
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let acc = '', buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, {stream:true});
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i).trim();
          buf = buf.slice(i+1);
          if (!line) continue;
          if (line.startsWith('data:')) {
            const data = line.slice(5).trim();
            if (data === '[DONE]') { buf = ''; break; }
            if (data && data !== '•') {
              acc += data;
              // тут позже повесим live-обновление пузыря
              // window.dispatchEvent(new CustomEvent('air4-stream-chunk',{detail:data}));
            }
          }
        }
      }

      // возвращаем ответ в том же формате, который ждёт UI
      return new Response(JSON.stringify({reply: acc}), {
        headers:{'Content-Type':'application/json'}
      });
    } catch (e) {
      console.error('shim-stream error', e);
      return origFetch(input, init);
    }
  };
})();
