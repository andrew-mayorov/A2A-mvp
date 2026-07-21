# Demo script

1. Start with `docker compose up --build` and open `http://127.0.0.1:8080`.
2. Point out the visible local-demo banner and current in-memory approver identity.
3. Create the prefilled need; explain that values come from `config/demo.toml`.
4. In the timeline show A1 discovery and direct signed RFQs to multiple A2 processes.
5. Compare Quotes, one rejected hard constraint and deterministic component scores.
6. Show optional LLM explanation; disable the provider and repeat to prove continuity.
7. Choose reject/request changes, then create another deal and approve with snapshot hash.
8. Show Purchase Intent, hash-chain anchor and successful Oracle verification.
9. Confirm that payment is `awaiting_customer_signature` and fulfillment is empty.
10. Perform the separate mock bank signature; then show fulfillment/documents.
11. Export Evidence Bundle and call Trust ledger integrity endpoint for the deal.

Negative demonstration: alter the snapshot hash, expire/revoke a mandate or repeat the
approve request. The backend must reject stale data or return the same artifact IDs,
never create another draft.
