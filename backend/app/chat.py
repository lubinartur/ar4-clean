from .memory.manager import MemoryManager

mm: MemoryManager | None = None  # общий инстанс, прилетит из main

def set_memory_manager(manager: MemoryManager):
    global mm
    mm = manager

SYSTEM_BASE = (
    "Ты — локальный ИИ ассистент AIR4. Помни цели и контекст. Отвечай кратко и точно."
)

def build_context(user_msg: str, top_k: int = 5, with_short_summary: bool = True) -> str:
    assert mm is not None, "MemoryManager is not initialized"
    long_hits = mm.retrieve(user_msg, k=top_k)
    long_block = "\n\n".join([f"[{i+1}] {h['text']}" for i, h in enumerate(long_hits)])
    short_block = mm.short_summary() if with_short_summary else mm.short_context()
    profile_block = mm.profile_text()
    return f"{SYSTEM_BASE}\n\n# PROFILE\n{profile_block}\n\n# SHORT\n{short_block}\n\n# LONG\n{long_block}"

def on_user_message(msg: str):
    assert mm is not None, "MemoryManager is not initialized"
    mm.push_short("user", msg)

def on_assistant_message(msg: str):
    assert mm is not None, "MemoryManager is not initialized"
    mm.push_short("assistant", msg)

def add_fact(text: str, meta=None):
    assert mm is not None, "MemoryManager is not initialized"
    return mm.ingest(text, meta or {"source":"chat_fact"})

