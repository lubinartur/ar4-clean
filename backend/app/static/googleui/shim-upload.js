(() => {
  // ---- Перехват fetch: переписываем старые пути UI на рабочие ----
  const origFetch = window.fetch;
  const rewrite = (u) => {
    try {
      let s = (typeof u === 'string') ? u : u.url;
      s = s
        .replace(/^http:\/\/127\.0\.0\.1:8000/, '')
        .replace(/^http:\/\/localhost:8000/, '')
        .replace(/\/api\/health\b/, '/health')
        .replace(/\/api\/chat\b/, '/chat')
        .replace(/\/send3\b/, '/chat/rag');
      if (!s.startsWith('/')) s = '/' + s;
      return s;
    } catch { return u; }
  };
  window.fetch = (input, init) => {
    if (typeof input === 'string') {
      return origFetch(rewrite(input), init);
    } else if (input instanceof Request) {
      return origFetch(new Request(rewrite(input.url), input), init);
    }
    return origFetch(input, init);
  };

  // ---- Drag&Drop загрузка в /ingest/file?tag=ui ----
  const postFile = async (file) => {
    const fd = new FormData();
    fd.append('file', file, file.name || 'upload.bin');
    try {
      const r = await fetch('/ingest/file?tag=ui', { method: 'POST', body: fd });
      if (!r.ok) throw new Error('upload failed: ' + r.status);
      console.log('[AIr4] upload ok', await r.json());
      // Автообработка: commit + process делать не нужно — /ingest/file уже триггерит.
    } catch (e) {
      console.error('[AIr4] upload error', e);
    }
  };

  const dropZone = document.body;
  dropZone.addEventListener('dragover', (ev) => { ev.preventDefault(); }, { passive: false });
  dropZone.addEventListener('drop', async (ev) => {
    ev.preventDefault();
    const files = ev.dataTransfer?.files;
    if (files && files.length) {
      for (const f of files) await postFile(f);
    }
  });

  console.log('[AIr4] shim loaded: fetch rewired, DnD uploader active');
})();
