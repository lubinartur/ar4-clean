from fastapi import HTTPException
import subprocess

def run_ollama(model: str, prompt: str, timeout: int = 120) -> str:
    """Запуск `ollama run <model> <prompt>` и возврат ответа модели.
    С таймаутом и аккуратной обработкой ошибок.
    """
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Ollama не найден в PATH.")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Ollama timeout.")

    if result.returncode != 0:
        err = (result.stderr or "Unknown error").strip()
        raise HTTPException(status_code=502, detail=f"Ollama error: {err}")

    return (result.stdout or "").strip()

