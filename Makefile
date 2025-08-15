.PHONY: dev fmt

dev:
	uvicorn backend.app.main:app --reload

fmt:
	python -m pip install --quiet ruff black && ruff check --fix backend || true && black backend

