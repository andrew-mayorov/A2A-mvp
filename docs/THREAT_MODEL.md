# Threat model

## Assets and adversaries

Assets: mandates, private keys, signed RFQ/Quote, approval evidence, supplier binding,
Purchase Intent, ledger integrity and payment draft. Attackers include a malicious A2,
compromised browser/user, cross-tenant user, poisoned document/Agent Card, network
attacker and compromised LLM provider.

| Threat | Current control | Residual work |
|---|---|---|
| Forged/tampered message | canonical JSON, SHA-256, Ed25519, key_id | KMS/HSM, CRL distribution |
| Replay/stale envelope | nonce, expiry, idempotency fields | persistent distributed nonce store |
| SSRF/metadata access | scheme/port/DNS/IP checks, metadata deny, no redirect | DNS pinning egress proxy |
| Prompt injection | separated trusted/untrusted blocks; LLM no critical tools | broader adversarial corpus |
| Stale approval | immutable snapshot and backend hash recompute | qualified electronic signature |
| Payment substitution | registry binding hash + Oracle checks | real bank recipient verification |
| Duplicate approval/draft | state guard, unique/idempotency records | multi-instance lock/reconciliation |
| Ledger modification | previous/current hash and verify endpoint | external anchor/WORM backup |
| IDOR/cross-tenant | demo profile isolation only | mandatory JWT tenant/object policy |
| Secret leakage | generated volume, SecretStr, no API return | per-agent volumes and log scanner |

## Trust boundaries

Browser→A1, A1↔A2, any service→LLM, any service→external URL, app→database,
Trusted Infrastructure→payment/EDO are independent boundaries. Presence in the ledger
does not make an event trusted; Oracle revalidates hashes, actors, mandate, recipient,
amount, currency, expiry and fraud decision.
