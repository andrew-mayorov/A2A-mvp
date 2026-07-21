# Configuration

Business values belong to versioned TOML/Registry/Mandate/Tool Manifest/PostgreSQL.
Secrets belong to environment variables or a secret provider.

| Source | Examples |
|---|---|
| `config/demo.toml` | demo IDs, suppliers, categories, currency, ranking, limits, policy |
| supplier JSON | catalog inventory/prices for each Demo A2 |
| environment | database URL, provider credentials/model/base URLs, runtime profile |
| generated volume | database password and demo private keys |

Production must use a separate config file: HTTPS-only egress, `production_like=true`,
no demo identities, non-demo issuer/audience, external secrets and per-agent keys. Empty
provider model/URL/allowlist values are configuration errors, not fallback instructions.
