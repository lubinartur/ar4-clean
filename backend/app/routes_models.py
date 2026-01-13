from __future__ import annotations

from fastapi import APIRouter, HTTPException
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models/ollama")
async def get_ollama_models():
    """
    Получает список моделей из Ollama API.
    Возвращает массив имен моделей.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            response.raise_for_status()
            data = response.json()
            
            # Извлекаем имена моделей из ответа
            models = []
            if isinstance(data, dict) and "models" in data:
                for model in data["models"]:
                    if isinstance(model, dict) and "name" in model:
                        models.append(model["name"])
            
            return {"models": models}
            
    except httpx.TimeoutException:
        logger.error("[MODELS] Timeout while fetching Ollama models")
        raise HTTPException(
            status_code=502,
            detail="Timeout while connecting to Ollama API"
        )
    except httpx.RequestError as e:
        logger.error("[MODELS] Request error while fetching Ollama models: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to Ollama API: {str(e)}"
        )
    except httpx.HTTPStatusError as e:
        logger.error("[MODELS] HTTP error while fetching Ollama models: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Ollama API returned error: {e.response.status_code}"
        )
    except Exception as e:
        logger.error("[MODELS] Unexpected error while fetching Ollama models: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected error: {str(e)}"
        )

