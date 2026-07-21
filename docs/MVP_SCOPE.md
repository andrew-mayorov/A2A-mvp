# MVP scope and completion status

## Implemented vertical slice

- separate A1 process and three separately configured A2 processes;
- direct signed RFQ/Quote A2A envelopes;
- deterministic Decimal ranking configured outside code;
- approve/reject/request-changes and immutable snapshot hash;
- Purchase Intent, SQL hash-chain anchor and integrity verification;
- Oracle verification and draft-only payment boundary;
- separate human bank-signature simulation before mock fulfillment;
- Evidence Bundle, deal timeline, outbox records and JSON Schemas;
- disabled/OpenRouter/GigaChat/Fake LLM ports with deterministic fallback;
- PostgreSQL Compose topology, development OIDC container and Alembic migrations;
- SSRF policy, tool risk boundary and basic security negative tests.

## Explicitly not production complete

- OIDC/JWT enforcement, BFF sessions and tenant-scoped object authorization;
- full passport/KYB/attestation/key-rotation onboarding UI/workflow;
- per-process HSM/KMS keys and production egress proxy/DNS pinning;
- real bank, ERP or EDO execution (all such adapters are clearly Mock/Demo);
- distributed outbox worker, DLQ/reconciliation and cross-process locks;
- full OpenTelemetry/Prometheus, rate limits, SBOM/container/secret scans;
- the complete E2E/security matrix from the target specification.

The prototype is suitable for architecture/demo validation with synthetic data. It
must not process real payments, contracts, credentials or personal data.
