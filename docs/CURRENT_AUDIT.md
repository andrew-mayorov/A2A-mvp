# Repository audit against target specification

Аудит выполнен до и во время миграции ветки `codex/a1-a2-trusted-infrastructure`.

| Компонент | Текущее состояние | Соответствие | Проблема | Риск | Рекомендуемое/выполненное изменение | Затронутые файлы |
|---|---|---|---|---|---|---|
| Topology | Был A1→A3→A2 | Исправлено в slice | A3 совмещал negotiation и trust | Central authority/lock-in | A1 напрямую вызывает независимые A2; A3 удалён | `a1_service.py`, `a2a_gateway.py`, `workflow/graph.py`, `compose.yaml` |
| Contracts | Неполные unversioned models | Частично | Не хватало passport/envelope/evidence contracts | Schema drift | Pydantic v2 contracts + exported JSON Schema | `domain/contracts.py`, `schemas/v1` |
| Signatures | Сообщения не были связаны со всеми context fields | Исправлено в A1↔A2 slice | Replay/substitution | Forged RFQ/Quote | Canonical payload hash + Ed25519 SignedEnvelope | `shared/security/*`, `suppliers/*` |
| Registry | Runtime list и старый onboarding | Частично | Нет полного production KYB/attestation workflow | Rogue supplier | Configured active demo passports; endpoint/card checks; production workflow backlog | `config/demo.toml`, `onboarding.py`, `trust_api.py` |
| Mandate | Проверка в основном на входе | Частично | Недостаточная revalidation | Excess authority | Recheck before RFQ, approval, intent, anchor, Oracle, draft | `domain/models.py`, `trust_infrastructure/service.py` |
| Ranking | Deterministic, но defaults в code | Исправлено | Business weights hardcoded | Unexplained selection | Decimal weights/version from TOML | `config.py`, `domain/ranking.py`, `config/demo.toml` |
| Approval | Snapshot был, decision limited | Исправлено в slice | Не было reject/changes и отдельного bank step | Hidden/stale approval | Immutable hash, three decisions, duplicate-safe approve | `services/deals.py`, frontend, tests |
| Ledger | Deal events, не строгий intent chain | Исправлено в slice | Mutable record could be mislabeled | Evidence tampering | Separate DatabaseHashChainAnchor + integrity endpoint | `trust_infrastructure/ledger.py`, migration 0004 |
| Oracle/payment | IDs создавались вместе с order | Исправлено в slice | Недостаточная verification boundary | Unauthorized payment | Oracle checks and payment draft only; human signature endpoint | `trust_infrastructure/service.py`, `api.py` |
| LLM | Provider branching and incomplete config | Исправлено в gateway | Provider/model fallback ambiguity | Prompt/control injection | LLMPort registry, disabled default, OpenRouter/GigaChat adapters | `services/llm.py`, `config.py` |
| SSRF | Onboarding trusted URLs | Частично | DNS/redirect/private IP risks | Metadata/internal access | OutboundPolicy, no redirects; connection pinning/rebinding proxy remains backlog | `shared/security/outbound.py`, `onboarding.py` |
| AuthN/AuthZ | Demo header only | Не соответствует production | OIDC container not yet enforced by API/BFF | IDOR/privilege escalation | Keep demo visibly isolated; implement JWT validation/object auth next | `compose.yaml`, `config/oidc.json`, `api.py` |
| Persistence | SQLite default, limited tables | Improved | Missing required entities/migrations | Data loss/mixed tenants | PostgreSQL runtime + Alembic artifact stores | `compose.yaml`, migrations 0001–0004 |
| Frontend | A3-oriented labels and constants | Improved | Hardcoded demo identity/data | Drift/XSS risk | Config endpoint, memory identity, direct flow and separate signature | `frontend/src/*` |
| Containers | Few hardening controls | Improved, unverified here | Root/read-write/secret risks | Container escape/leak | non-root apps, read-only, cap-drop, generated secrets | Dockerfiles, `compose.yaml`, `.dockerignore` |
| Tests/CI | Basic unit/API tests | Partial | Security/E2E matrix incomplete | Regression blind spots | Added signature/SSRF/tool/approval tests; CI expansion backlog | `tests/*`, `.github/workflows/*` |

## Highest residual risks

1. OIDC is present for development, but JWT issuer/audience/tenant enforcement is not
   wired into every endpoint.
2. Demo agents share one generated key volume; production requires per-agent secret
   mounts/HSM/KMS and isolated identities.
3. Docker Compose was not runnable in the current execution environment because the
   Docker CLI is absent.
4. Full onboarding, reconciliation/dead-letter workers, rate limiting, OpenTelemetry
   export and the requested negative-test matrix are not complete.
