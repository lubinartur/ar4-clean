document.addEventListener('htmx:afterRequest', () => {
  const box = document.getElementById('messages');
  if (box) box.scrollTop = box.scrollHeight;
});
const ta = document.getElementById('message');
if (ta) ta.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('chatForm')?.querySelector('button[type=submit]')?.click();
  }
});
