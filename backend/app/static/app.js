// static/app.js — UI: Session/Model/System/Stream + RAG + Sources + Theme
(() => {
  const $ = (id) => document.getElementById(id);
  const LS = {
    useRag: 'air4.chat.use_rag',
    kMem:   'air4.chat.k_memory',
    sid:    'air4.chat.session_id',
    model:  'air4.chat.model',
    sys:    'air4.chat.system',
    stream: 'air4.chat.stream',
    theme:  'air4.theme'
  };

  // ---------- theme ----------
  function applyTheme(t){ document.documentElement.className = t === 'dark' ? 'dark' : 'light'; }
  function toggleTheme(){
    const cur = localStorage.getItem(LS.theme) || 'light';
    const next = cur === 'dark' ? 'light' : 'dark';
    localStorage.setItem(LS.theme, next); applyTheme(next);
  }

  // ---------- utils ----------
  function genSid(){ return Math.random().toString(36).slice(2,14); }
  function escapeHtml(s){ return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function isGreeting(t){ const q=String(t||'').trim(); return q.length<5||/^(hi|hello|hey|привет|здрав|qq|ку|yo|sup)\b/i.test(q); }
  function normalizeText(t){ return String(t||'').split(/\s+/).join(' ').trim(); }

  function bubble(role, text, memoryUsed){
    const box = document.createElement('div'); box.className='msg '+role;
    const roleEl = document.createElement('div'); roleEl.className='role '+role; roleEl.textContent = role==='user'?'U':'A';
    const bubble = document.createElement('div'); bubble.className='bubble';
    const meta = document.createElement('div'); meta.className='meta'; meta.textContent = role;
    const content = document.createElement('div'); content.className='content'; content.innerHTML = escapeHtml(text||'');
    bubble.append(meta, content);

    if (Array.isArray(memoryUsed) && memoryUsed.length){
      const src = document.createElement('div'); src.className='sources';
      src.innerHTML = `<div class="title">Sources:</div>
        <ul>${memoryUsed.map(s=>`<li>${escapeHtml(String(s))}</li>`).join('')}</ul>`;
      bubble.appendChild(src);
    }
    box.append(roleEl, bubble); $('messages').appendChild(box);
    $('messages').scrollTop = $('messages').scrollHeight;
    return {box, bubble, content};
  }

  function saveState(){
    $('use-rag') && localStorage.setItem(LS.useRag, $('use-rag').checked ? '1':'0');
    $('k-memory') && localStorage.setItem(LS.kMem, String(Number($('k-memory').value||4)));
    if ($('session-id')) { const v=$('session-id').value.trim(); if(v) localStorage.setItem(LS.sid, v); }
    $('model') && localStorage.setItem(LS.model, $('model').value||'');
    $('system') && localStorage.setItem(LS.sys, $('system').value||'');
    $('stream') && localStorage.setItem(LS.stream, $('stream').checked?'1':'0');
  }

  function loadState(){
    applyTheme(localStorage.getItem(LS.theme)||'light');
    const useRag = localStorage.getItem(LS.useRag); if(useRag!==null&&$('use-rag')) $('use-rag').checked = useRag==='1';
    const k = localStorage.getItem(LS.kMem); if(k&&$('k-memory')) $('k-memory').value = k;
    const sid = localStorage.getItem(LS.sid); if($('session-id')) $('session-id').value = sid || genSid();
    const sys = localStorage.getItem(LS.sys); if(sys&&$('system')) $('system').value = sys;
    const stream = localStorage.getItem(LS.stream); if(stream!==null&&$('stream')) $('stream').checked = stream==='1';
  }

  async function loadModels(){
    try{
      const r = await fetch('/models',{cache:'no-store'}); const arr = await r.json();
      const sel = $('model'); sel.innerHTML='';
      for(const m of arr){ const opt=document.createElement('option'); opt.value=m.id; opt.textContent=m.title||m.id; sel.appendChild(opt); }
      let chosen = localStorage.getItem(LS.model);
      if(!chosen){ try{ const h=await fetch('/health',{cache:'no-store'}).then(r=>r.json()); chosen=h?.model||''; }catch{} }
      if(chosen) sel.value = chosen;
    }catch{
      const sel=$('model'); if(sel){ sel.innerHTML='<option value="">(failed to load)</option>'; }
    }
  }

  // client-side memory for stream mode
  async function getMemoryBlocks(query,k){
    const out=[]; try{
      const u=new URL('/memory/search',location.origin); u.searchParams.set('q',query); u.searchParams.set('k',String(k));
      const j = await fetch(u,{cache:'no-store'}).then(r=>r.json());
      const items = j.results||j.data||j.items||[]; const seen=new Set();
      for(const r of items){
        const txt=r.text||r.chunk||r.content||r.value||''; const score=Number(r.score||0);
        if(!Number.isFinite(score) || score>=0.60){
          const norm=normalizeText(txt); if(norm && !seen.has(norm)){ seen.add(norm); out.push(txt); }
        }
      }
    }catch{} return out;
  }

  async function onSubmit(e){
    e.preventDefault();
    const input = $('message'); const text=(input.value||'').trim(); if(!text) return false;
    saveState();

    bubble('user', text);
    const useStream = $('stream').checked;
    const sid = $('session-id').value || genSid();
    const model = $('model').value || null;
    const system = $('system').value || '';
    const useRag = $('use-rag').checked;
    const k = Number($('k-memory').value || 4);

    input.value=''; $('send-btn').disabled=true;

    if(useStream){
      // STREAM: /chat (client RAG)
      let memoryBlocks=[]; if(useRag && !isGreeting(text)){ memoryBlocks = await getMemoryBlocks(text, k); }
      const systemParts = []; if(system && system.trim()) systemParts.push(system.trim());
      if(memoryBlocks.length){ systemParts.push('Relevant context:\n'+memoryBlocks.join('\n\n---\n')); }
      const systemPayload = systemParts.length ? systemParts.join('\n\n') : null;

      const {content, box} = bubble('assistant','');
      try{
        const payload={message:text, model, stream:true, session:sid, system:systemPayload};
        const res = await fetch('/chat',{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
        if(!res.ok || !res.body){ content.innerHTML = escapeHtml(`⚠️ Error ${res.status}`); }
        else{
          const reader=res.body.getReader(); const dec=new TextDecoder();
          while(true){ const {value,done}=await reader.read(); if(done) break; content.innerHTML += escapeHtml(dec.decode(value)); $('messages').scrollTop = $('messages').scrollHeight; }
        }
      }catch{ content.innerHTML = escapeHtml('⚠️ Network error'); }
      finally{
        if(memoryBlocks.length){
          const src=document.createElement('div'); src.className='sources';
          src.innerHTML = `<div class="title">Sources:</div><ul>${memoryBlocks.map(s=>`<li>${escapeHtml(String(s))}</li>`).join('')}</ul>`;
          box.querySelector('.bubble').appendChild(src);
        }
        $('session-id').value = sid; localStorage.setItem(LS.sid, sid);
        $('send-btn').disabled=false; $('message').focus();
      }
    }else{
      // NON-STREAM: /ui/chat/send (server RAG)
      try{
        const res = await fetch('/ui/chat/send',{
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({ message:text, session_id:sid, use_rag:useRag, k_memory:k })
        });
        if(!res.ok){ bubble('assistant', `⚠️ Error ${res.status}`); }
        else{
          const data = await res.json();
          if(data.session_id){ $('session-id').value=data.session_id; localStorage.setItem(LS.sid,data.session_id); }
          bubble('assistant', data.reply || '', data.memory_used || []);
        }
      }catch{ bubble('assistant','⚠️ Network error'); }
      finally{ $('send-btn').disabled=false; $('message').focus(); }
    }
    return false;
  }

  async function clearSession(){
    const sid=($('session-id').value||'').trim(); if(!sid) return;
    try{ await fetch(`/sessions/${encodeURIComponent(sid)}/clear`,{method:'POST'}); $('messages').innerHTML=''; }catch{}
  }
  function copySession(){ const sid=($('session-id').value||'').trim(); if(!sid) return; navigator.clipboard?.writeText(sid); }
  function newSession(){ const sid=genSid(); $('session-id').value=sid; localStorage.setItem(LS.sid,sid); $('messages').innerHTML=''; }

  function bindHotkeys(){
    const input=$('message');
    input.addEventListener('keydown', (e)=>{ if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){ e.preventDefault(); $('chat-form').requestSubmit(); } });
  }
  function autosizeTextarea(){
    const ta=$('message'); const resize=()=>{ ta.style.height='auto'; ta.style.height=(ta.scrollHeight>240?240:ta.scrollHeight)+'px'; };
    ['input','change'].forEach(ev=>ta.addEventListener(ev,resize)); resize();
  }
  function bindToolbar(){
    $('btn-new')?.addEventListener('click', newSession);
    $('btn-copy')?.addEventListener('click', copySession);
    $('btn-clear')?.addEventListener('click', clearSession);
    $('use-rag')?.addEventListener('change', saveState);
    $('k-memory')?.addEventListener('change', saveState);
    $('model')?.addEventListener('change', saveState);
    $('system')?.addEventListener('change', saveState);
    $('stream')?.addEventListener('change', saveState);
    $('themeBtn')?.addEventListener('click', toggleTheme);
  }

  // public API
  window.app = {
    async init(){
      loadState(); await loadModels();
      if(!$('model').value){ const first=$('model').querySelector('option'); if(first) $('model').value=first.value; }
      bindToolbar(); bindHotkeys(); autosizeTextarea();
      $('message')?.focus(); $('chat-form')?.addEventListener('submit', onSubmit);
    }
  };
})();
