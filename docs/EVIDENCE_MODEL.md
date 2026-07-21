# Evidence model

Evidence Bundle reconstructs need/mandate, RFQ/Quote comparison, immutable approval,
human decision, Purchase Intent, ledger anchor, Oracle result, payment draft/signature
status, fulfillment, document hashes, policy/fraud decisions, timeline and outbox.

Each event carries actor, timestamp, correlation/causation/message IDs and payload hash.
Ledger anchors contain sequence, previous hash, current hash and anchored payload hash.
The integrity endpoint recomputes the chain; it does not assert business truth. Oracle
provides that separate semantic verification before a payment draft can exist.
