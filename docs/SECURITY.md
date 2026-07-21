# Security guidance

- Never commit `.env`, PEM files, credentials or generated bootstrap volumes.
- Keep `LLM_PROVIDER=disabled` unless a provider is explicitly configured and approved.
- Production network profile must allow HTTPS only, public destinations and approved
  ports/hostnames through an egress proxy.
- Replace demo filesystem Ed25519 with per-agent KMS/HSM providers and audited rotation.
- Replace demo identity header with OIDC authorization-code + PKCE through a BFF; verify
  issuer, signature, audience, time, resource, scope, role and tenant on every request.
- Apply tenant/object predicates in repositories; never accept tenant from request body.
- Critical/legal/financial tools must remain unavailable to model callers.
- Payment integration may create/hold a draft only; execution requires bank-controlled
  human signature outside this application.

Security incident actions: enable financial kill switch, freeze deal, revoke mandate,
suspend agent, rotate key, retain evidence, and reconcile all idempotency/outbox records.
