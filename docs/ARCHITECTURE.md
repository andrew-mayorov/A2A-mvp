# Target architecture

## Decision

A1 владеет потребностью, discovery, прямым A2A RFQ, deterministic validation/ranking
и представлением результата человеку. A2 владеет каталогом и Quote. Trusted
Infrastructure только проверяет полномочия, риск и юридически значимые переходы.

```mermaid
flowchart TB
  UI["Frontend / human"] --> A1["A1 Buyer Agent"]
  A1 <-->|"signed RFQ / Quote"| A21["A2 Supplier 1"]
  A1 <-->|"signed RFQ / Quote"| A22["A2 Supplier 2+"]
  A1 --> TI["Trusted Infrastructure"]
  TI --> DB["PostgreSQL / hash chain"]
  TI --> TOOLS["ERP / EDO / payment adapters"]
```

Нет узла A3. Trusted Infrastructure не выбирает Quote и не ведёт переговоры.

## Process boundaries

| Process | Responsibility | Forbidden authority |
|---|---|---|
| A1 | need, registry query, signed RFQ, validation, ranking, UI | execute payment, autonomous contract signature |
| A2.N | own catalog/inventory, signed Quote | buyer approval, payment |
| Trust API | registry view, readiness, ledger integrity | negotiation, supplier selection |
| Trust modules | mandate/policy/fraud/approval/intent/oracle/draft | changing ranking or offer |
| Model Gateway | optional parsing/explanation | any legal/financial decision |

Trusted modules currently share code and database as a modular monolith. A1 invokes
the control application service in-process; the separate Trust API exposes registry
and ledger verification. Replacing that call with an authenticated port is the next
extraction step and does not change domain contracts.

## Dependency rule

`API/adapters → application → domain`. Domain models do not import FastAPI,
SQLAlchemy, A2A SDK, LangChain or a database implementation.

## Purchase sequence

```mermaid
sequenceDiagram
  participant H as Human
  participant A1 as A1 Buyer
  participant A2 as A2 Suppliers
  participant T as Trust controls
  H->>A1: Need + mandate
  A1->>T: Validate mandate / registry
  A1->>A2: Signed RFQ (direct A2A)
  A2-->>A1: Signed Quote
  A1->>A1: Validate and deterministic rank
  A1-->>H: Comparison + immutable snapshot
  H->>A1: Decision + snapshot hash
  A1->>T: Intent, anchor, Oracle verification
  T-->>H: Payment draft only
  H->>T: Separate bank-signature simulation
  T-->>A1: Fulfillment allowed
```

## Deal state

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> awaiting_approval: valid quotes ranked
  draft --> failed: mandate or quote failure
  awaiting_approval --> rejected: reject
  awaiting_approval --> changes_requested: request changes
  awaiting_approval --> payment_signature_required: approve matching snapshot
  payment_signature_required --> completed: human bank signature
  payment_signature_required --> payment_signature_required: duplicate approval/signature
```

## Trust boundaries and data flow

- Browser input, A2 messages, Agent Cards, documents and LLM output are untrusted.
- SignedEnvelope uses canonical JSON, payload SHA-256 and replaceable Ed25519 provider.
- Agent endpoints pass centralized scheme/port/DNS/IP validation; redirects are disabled.
- Payment recipient comes from Registry binding hash, never free-form Quote text.
- PostgreSQL ledger events are an append-only hash chain, explicitly not a blockchain.
- Tenant enforcement is partial in this MVP; production OIDC/BFF and row-level object
  authorization remain mandatory before real data.
