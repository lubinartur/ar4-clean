# Phase-10: RAG quality — PR

## What
- Добавлены шумовые документы в `tests/rag_corpus/docs/noise` для устойчивости извлечения.
- Makefile с таргетами:
  - `serve` — запуск API (`uvicorn`) и ожидание `/health`.
  - `smoke-phase10` — локальный RAG smoke с порогом `avg p@3 ≥ 0.7`.
  - `smoke-ci` — последовательность для CI (serve → smoke → kill).
- GitHub Actions workflow `.github/workflows/rag-smoke.yml`:
  - Поднимает `uvicorn`, проверяет `/health=200` и `/__routes=404`.
  - Гоняет `scripts/smoke_phase10_rag.sh`, валит job при `avg p@3 < 0.7`.
  - Загружает `.smoke.log` как artifact.
- README дополнен секцией **“Phase‑10: RAG smoke”** (как запускать, критерий «зелёного», где корпус).
- Временный роут `/__routes` отсутствует (404) — зафиксировано проверками.

## Why
- Нужна автоматическая регрессия качества RAG в локальной разработке и CI.
- Порог `avg p@3 ≥ 0.7` — минимально допустимый «зелёный» сигнал на шумном корпусе, защищает от деградаций при изменениях кода/корпуса.

## How to verify
1) Локально (ожидается зелёный порог):
```bash
make serve
make smoke-phase10
make kill-serve
```

2) Инварианты API:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health   # 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/__routes # 404
```

3) CI:
- Открыть GitHub → Actions → **RAG Smoke (Phase-10)**.
- Джоб зелёный; artifact `smoke-log` содержит строку `avg p@3 = …` c значением ≥ 0.7.

## Definition of Done — Phase‑10 (RAG quality)
- [x] Корпус `tests/rag_corpus/` присутствует; `queries.tsv` валиден.
- [x] Шумовые документы добавлены в `tests/rag_corpus/docs/noise`.
- [x] Локально `scripts/smoke_phase10_rag.sh` стабильно даёт `avg p@3 ≥ 0.7`.
- [x] Makefile с таргетами `serve`, `smoke-phase10`, `smoke-ci`.
- [x] Workflow `.github/workflows/rag-smoke.yml` валит при `avg p@3 < 0.7`, грузит лог-артефакт.
- [x] README дополнен секцией «Phase‑10: RAG smoke».
- [x] `/__routes` отсутствует (404).
- [x] Готово к релизу `v0.10.0-phase10` (после merge в `main`).
