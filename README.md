# Trusted B2B A2A Procurement MVP

Рабочая ветка мигрирует проект со схемы `A1 → A3 → A2` на прямое подписанное
взаимодействие `A1 Buyer Agent ↔ A2 Supplier Agent`. Отдельного A3-агента нет.
Registry, mandate/policy/fraud controls, approval, append-only hash chain, Oracle и
Payment Gatekeeper находятся в Trusted Infrastructure и не ведут переговоры.

## Быстрый запуск

Требования: Docker Engine с Compose v2 и свободные порты 8000, 8080, 8081, 8100.

```bash
cp .env.example .env
docker compose up --build
```

После старта:

| Сервис | URL |
|---|---|
| Frontend | http://127.0.0.1:8080 |
| A1 Swagger | http://127.0.0.1:8100/docs |
| Trusted Infrastructure Swagger | http://127.0.0.1:8000/docs |
| Development OIDC | http://127.0.0.1:8081/default/.well-known/openid-configuration |
| A1 readiness | http://127.0.0.1:8100/ready |
| Trust readiness | http://127.0.0.1:8000/ready |

Bootstrap-контейнер при каждом новом volume генерирует пароль PostgreSQL и
Ed25519 demo-ключи. Секреты не находятся в Git или Docker image.

## Demo flow

1. Откройте frontend и создайте потребность из конфигурируемого demo-profile.
2. A1 проверит мандат и напрямую отправит подписанный RFQ минимум двум A2.
3. A2 проверят envelope и вернут подписанные Quote.
4. A1 применит hard constraints и воспроизводимый Decimal-ranking.
5. Нажмите approve, reject или request changes. Approve требует точный snapshot hash.
6. После approve создаются Purchase Intent, ledger anchor, Oracle verification и только
   payment draft.
7. Отдельно подтвердите mock банковскую подпись. Лишь после этого demo формирует
   fulfillment/documents.
8. Выгрузите Evidence Bundle и проверьте timeline.

Автоматического списания денег, автономной подписи договора и скрытого approval нет.

## LLM providers

Основной flow работает с `LLM_PROVIDER=disabled`. Для OpenRouter или GigaChat
заполните `.env`; модели, URL, upstream providers и fallback не находятся в
business logic. Неуказанная модель или provider не выбираются автоматически.

```bash
LLM_PROVIDER=openrouter docker compose up --build
```

```bash
LLM_PROVIDER=gigachat docker compose up --build
```

Переменные и ограничения описаны в [docs/LLM_PROVIDERS.md](docs/LLM_PROVIDERS.md).

## Выполненные локальные проверки

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src/sber_a2a
uv run pytest -q
cd frontend && npm ci && npm run lint && npm run build
DATABASE_URL=sqlite+aiosqlite:////tmp/a2a-migration.db uv run alembic upgrade head
```

В текущей среде Docker CLI отсутствовал, поэтому Compose build/smoke здесь не
выполнялся. Это открытый verification item, а не заявленный успех.

## Конфигурация и структура

- `config/demo.toml` — только local demo business/profile data;
- `config/suppliers/*.json` — независимые demo-каталоги A2;
- `src/sber_a2a/domain` — framework-independent contracts and rules;
- `src/sber_a2a/shared/security` — canonicalization, Ed25519, outbound policy;
- `src/sber_a2a/trust_infrastructure` — bounded control contexts;
- `schemas/v1` — versioned JSON Schemas;
- `migrations` — PostgreSQL/SQLite-compatible Alembic revisions.

Начните с [архитектуры](docs/ARCHITECTURE.md), [аудита](docs/CURRENT_AUDIT.md),
[demo script](docs/DEMO_SCRIPT.md) и [ограничений MVP](docs/MVP_SCOPE.md).
