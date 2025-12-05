(function () {
  const el = (function ensureBadge(){
    let n = document.getElementById('air4-status');
    if (!n) {
      n = document.createElement('div');
      n.id = 'air4-status';
      n.style.cssText = 'position:fixed;left:12px;bottom:12px;padding:6px 10px;border-radius:10px;background:rgba(0,0,0,.35);backdrop-filter:blur(6px);font:12px/1.3 ui-monospace,monospace;color:#cbd5e1;z-index:9999';
      n.textContent = 'AIR4: checking…';
      document.body.appendChild(n);
    }
    return n;
  })();

  fetch('/health')
    .then(r => r.json())
    .then(j => {
      console.log('AIR4 health:', j);
      const model = j.model || j.llm || j.LLM || '—';
      const mem   = j.memory_backend || j.memory || '—';
      el.textContent = `AIR4 • ${model} • mem:${mem}`;
    })
    .catch(err => {
      console.warn('AIR4 status failed:', err);
      el.textContent = 'AIR4 • offline';
    });
})();
