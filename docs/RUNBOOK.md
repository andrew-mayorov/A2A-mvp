# Operations runbook

## Readiness order

Bootstrap → PostgreSQL → migrations → A2 suppliers → Trust API → A1 → frontend.
`/health` is process liveness; `/ready` includes database/registry dependencies. LLM
failure degrades explanations only and must not make procurement unavailable.

## Triage

- No Quotes: check A2 health, registry status, SignedEnvelope expiry/key and A1 logs by
  correlation/deal ID.
- Approval conflict: compare current and submitted snapshot hashes; never override it.
- Oracle denial: inspect mandate, agent state, binding, amount/currency and fraud reason.
- Ledger integrity false: freeze the deal and preserve database/backups for investigation.
- Provider failure: set `LLM_PROVIDER=disabled`; deterministic ranking continues.

## Recovery

Do not delete or edit ledger/outbox rows. Restore PostgreSQL, verify migrations and hash
chains, replay only pending idempotent outbox messages, then reconcile artifacts by deal.
