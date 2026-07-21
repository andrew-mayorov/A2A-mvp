# LLM providers

The `LLMPort` exposes `parse_need`, `explain_comparison`, `summarize_risks` and
`healthcheck`. Provider selection happens once through a registry/DI factory.

## Disabled

`LLM_PROVIDER=disabled` is the default and supports the complete purchase flow.

## OpenRouter

Set API key, explicit model, base URL, allowed models, allowed upstream providers,
application URL/title, retention policy, timeout/retry/token/temperature limits. Unknown
models and implicit upstream fallback are rejected. Structured output must use JSON
Schema when supported and is always revalidated by Pydantic.

## GigaChat

Set credentials or access token, explicit model, scope, OAuth URL, API base URL, CA
bundle/TLS verification and bounded timeouts/retries. Credentials/tokens are SecretStr
and never logged. The current adapter delegates token caching to the official client;
an explicit observable stampede-protected token port is production backlog.

Prompts use separate `SYSTEM POLICY`, `TRUSTED CONTEXT`, `UNTRUSTED DATA` and
`EXPECTED JSON SCHEMA` blocks. Supplier text/documents never become system instructions.
Any provider error falls back to deterministic content.
