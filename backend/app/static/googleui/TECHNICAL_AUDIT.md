# 🔍 Технический аудит AIR4 Frontend (v0.13)

**Дата:** 2025-01-XX  
**Версия:** 0.13  
**Статус:** Ingestion + RAG работают

---

## 📊 ОБЩАЯ ОЦЕНКА

**Архитектура:** 6/10  
**Код качество:** 5/10  
**Поддерживаемость:** 4/10  
**Производительность:** 6/10  
**DX (Developer Experience):** 5/10

---

## 🚨 P0 — КРИТИЧЕСКИЕ ПРОБЛЕМЫ (исправить немедленно)

### 1. **Отсутствующий метод `deleteMemory`**
**Файл:** `pages/Memory.tsx:50`  
**Проблема:** Вызывается `air4.deleteMemory(id)`, но метода нет в `air4Service.ts`

```typescript
// ❌ Текущий код (Memory.tsx:50)
const success = await air4.deleteMemory(id);

// ✅ Решение: добавить в air4Service.ts
async deleteMemory(id: string): Promise<boolean> {
  if (this.isOfflineMode) return false;
  try {
    const res = await fetch(`${API_BASE}/memory/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    return res.ok && (await res.json()).ok;
  } catch (e) {
    return false;
  }
}
```

**Приоритет:** P0 — ломает функциональность

---

### 2. **Дублирование структуры проекта**
**Проблема:** Есть две параллельные структуры:
- Корневая: `App.tsx`, `pages/`, `components/`, `services/`
- `src/`: `src/App.tsx`, `src/pages/`, `src/components/`, `src/services/`

**Последствия:**
- Неясно, какая версия используется
- Риск редактирования неактивных файлов
- Увеличение размера репозитория

**Решение:**
```bash
# Удалить src/ если не используется, или наоборот
# Проверить, что импортируется в index.tsx
```

**Приоритет:** P0 — путаница в разработке

---

### 3. **Хардкод API_BASE**
**Файлы:** `services/air4Service.ts:4`, `src/services/air4Service.ts:4`  
**Проблема:** `const API_BASE = 'http://127.0.0.1:8000';` захардкожен

**Решение:**
```typescript
// ✅ Создать config/env.ts
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

// Или через .env
// VITE_API_BASE=http://localhost:8000
```

**Приоритет:** P0 — блокирует деплой на другие хосты

---

## ⚠️ P1 — ВАЖНЫЕ ПРОБЛЕМЫ (исправить в ближайшее время)

### 4. **Дублирование источников состояния**
**Проблема:** Два источника правды:
- `useSettings()` — хранит в `localStorage` (`air4-core-settings-v1`)
- `air4Service` — хранит в `localStorage` (`air4_config`)

**Конфликты:**
- `activeModel` синхронизируется вручную
- `responseStyle` дублируется
- Риск рассинхронизации

**Решение:**
```typescript
// ✅ Унифицировать через Context или один источник
// Вариант 1: air4Service как единственный источник
// Вариант 2: React Context + useReducer
```

**Приоритет:** P1 — техдолг, риск багов

---

### 5. **Избыточный polling**
**Проблема:** Множественные интервалы:
- `Sidebar.tsx:56` — каждые 2s (сессии)
- `Chat.tsx:71` — каждые 5s (статистика)
- `Ingest.tsx:21` — каждые 1s (очередь)
- `History.tsx:23` — каждые 3s (сессии)

**Решение:**
```typescript
// ✅ Использовать WebSocket или EventSource
// ✅ Или единый polling service с debounce
// ✅ Или React Query с smart refetch
```

**Приоритет:** P1 — нагрузка на backend, батарея

---

### 6. **Слабая обработка ошибок**
**Проблема:**
- Много `try/catch` с пустыми блоками
- Нет централизованного error boundary
- Пользователь не видит ошибки

**Примеры:**
```typescript
// ❌ services/air4Service.ts:389
catch (e) {
    // Don't set offline mode here to avoid race conditions...
    return [];
}

// ✅ Решение:
catch (e) {
    console.error('[Memory] Search failed', e);
    // Показать toast или fallback UI
    return [];
}
```

**Приоритет:** P1 — плохой UX при ошибках

---

### 7. **Дублирование типов**
**Проблема:** `types.ts` в корне и `src/types.ts` — могут расходиться

**Решение:** Оставить один файл, удалить дубликат

**Приоритет:** P1 — риск рассинхронизации типов

---

### 8. **Мертвый код**
**Файл:** `App.tsx:82`
```typescript
if (false && !isSetup) {
  return <Welcome onComplete={() => setIsSetup(true)} />;
}
```

**Решение:** Удалить или включить функциональность

**Приоритет:** P1 — мусор в коде

---

## 📝 P2 — УЛУЧШЕНИЯ (можно отложить)

### 9. **Дублирование CSS анимаций**
**Файл:** `global.css` — `@keyframes dotPulse` объявлен дважды

**Решение:** Удалить дубликат

---

### 10. **Нет TypeScript strict mode**
**Файл:** `tsconfig.json`  
**Проблема:** Нет `"strict": true`

**Решение:**
```json
{
  "compilerOptions": {
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

---

### 11. **Нет тестов**
**Проблема:** Нет unit/integration тестов

**Решение:** Добавить Vitest + React Testing Library

---

### 12. **Нет ESLint/Prettier**
**Проблема:** Нет линтера, форматирование неконсистентное

**Решение:**
```json
// .eslintrc.json
{
  "extends": ["react-app", "prettier"],
  "rules": {
    "no-console": "warn"
  }
}
```

---

### 13. **Имитация стриминга вместо реального**
**Файл:** `services/air4Service.ts:680-688`
```typescript
// ❌ Имитация стриминга
for (let i = 0; i < reply.length; i += chunkSize) {
    const chunk = reply.slice(i, i + chunkSize);
    yield { chunk };
    await new Promise(r => setTimeout(r, 10));
}
```

**Проблема:** Backend возвращает полный ответ, frontend имитирует стриминг

**Решение:** Использовать реальный SSE/WebSocket стриминг с backend

---

### 14. **Нет мемоизации тяжелых вычислений**
**Файл:** `components/Sidebar.tsx:116-146`  
**Проблема:** `groupedHistory` пересчитывается на каждый render

**Решение:**
```typescript
const groupedHistory = useMemo(() => {
  return history.reduce(/* ... */);
}, [history]);
```

---

### 15. **Нет debounce для поиска**
**Файл:** `pages/Memory.tsx:63-68`  
**Проблема:** Debounce есть, но можно улучшить

**Решение:** Использовать `useDebounce` hook или библиотеку

---

## ✅ ЧТО ОСТАВИТЬ КАК ЕСТЬ

1. **Архитектура компонентов** — логичное разделение на pages/components
2. **Стилизация** — хороший glass-morphism UI
3. **Структура сервиса** — `air4Service` как центральный API клиент
4. **Офлайн режим** — хорошая обработка offline состояния
5. **Типизация** — в целом хорошая, есть TypeScript

---

## 🔧 КОНКРЕТНЫЕ РЕКОМЕНДАЦИИ

### Немедленно (P0):
1. ✅ Добавить `deleteMemory` в `air4Service`
2. ✅ Удалить дублирующую структуру (`src/` или корневую)
3. ✅ Вынести `API_BASE` в env/config

### В ближайшее время (P1):
4. ✅ Унифицировать управление состоянием (Context или один источник)
5. ✅ Оптимизировать polling (WebSocket/EventSource)
6. ✅ Добавить error boundaries и обработку ошибок
7. ✅ Удалить мертвый код (`if (false)`)

### Позже (P2):
8. ✅ Добавить тесты
9. ✅ Настроить ESLint/Prettier
10. ✅ Включить TypeScript strict mode
11. ✅ Реальный стриминг вместо имитации

---

## 📈 МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ

**Текущие проблемы:**
- 4 активных polling интервала (1-5s каждый)
- Нет мемоизации тяжелых вычислений
- Дублирование рендеров из-за множественных useState

**Ожидаемый эффект после оптимизации:**
- Снижение нагрузки на backend на ~70%
- Улучшение времени отклика UI на ~30%
- Снижение потребления батареи на мобильных

---

## 🎯 ПРИОРИТЕТЫ РЕФАКТОРИНГА

**Фаза 1 (1-2 дня):**
- P0 проблемы
- Унификация состояния
- Базовый error handling

**Фаза 2 (3-5 дней):**
- Оптимизация polling
- Мемоизация
- Удаление дубликатов

**Фаза 3 (1-2 недели):**
- Тесты
- Линтинг
- Реальный стриминг

---

## 📚 ДОПОЛНИТЕЛЬНЫЕ ЗАМЕЧАНИЯ

### Backend API контракт
- Проверить, что `/chat` endpoint поддерживает все параметры из `coreSettings`
- Убедиться, что `/memory/delete` существует (или добавить)
- Проверить CORS настройки для production

### Безопасность
- `localStorage` не шифруется — рассмотреть для чувствительных данных
- Нет валидации входных данных перед отправкой на backend

### Доступность
- Нет ARIA labels
- Нет keyboard navigation для всех элементов
- Нет screen reader поддержки

---

**Аудит подготовлен:** AI Assistant  
**Следующий шаг:** Обсудить приоритеты с командой

