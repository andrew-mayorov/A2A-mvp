# MCP and Tool Runtime security

MCP is agent-to-tool only, not the A1↔A2 transaction protocol. Demo MCP exposes
read-only supplier/deal tools. State-changing/legal/financial operations go through the
ToolRuntime authentication, tenant, Registry, mandate, scope, JSON Schema, fraud,
idempotency, execution/output-validation, audit and ledger sequence.

Production MCP requires OAuth 2.1 resource/audience validation, per-tool scopes and a
separate downstream token. Token passthrough is forbidden. Missing/invalid token is 401;
valid token without scope/role is 403. Model callers cannot access legal, financial or
critical tools even when a manifest accidentally lists them.
