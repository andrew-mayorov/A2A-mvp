# Migration guide: A3-centric to direct A1↔A2

## Mapping

| Former A3 responsibility | New owner |
|---|---|
| Supplier discovery | A1 queries Agent Registry |
| RFQ/Quote relay | Direct signed A1↔A2 A2A |
| Validation/ranking | Deterministic A1 domain service |
| Mandate/policy/fraud | Trusted Infrastructure controls |
| Human decision | Approval Service with immutable snapshot |
| Intent/evidence | Deal Ledger + anchor port |
| Payment preparation | Oracle Gateway + Payment Gatekeeper draft |
| LLM calls | Non-authoritative Model Gateway |

## Incremental plan

1. Freeze old A3 message contracts and add correlation IDs.
2. Register A1/A2 keys/endpoints and publish versioned Agent Cards.
3. Dual-run A1 direct RFQ in shadow mode; compare Quotes/ranking.
4. Move ranking and hard constraints to A1; Trust only returns decisions.
5. Require snapshot-hash approval and create Purchase Intent.
6. Switch payment integration to verified draft-only path.
7. Disable A3 negotiation endpoints and retain read-only historical evidence.
8. Remove A3 deployment after reconciliation and audit sign-off.

Rollback means routing new deals to the previous version; never rewrite already
anchored events. Existing deals finish under the protocol version recorded in their
Evidence Bundle.
