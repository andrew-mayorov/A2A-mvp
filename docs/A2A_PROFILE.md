# A2A procurement profile

A1 sends `a2a.procurement.rfq@1.0.0` as a SignedEnvelope data artifact. A2 returns
`a2a.procurement.quote@1.0.0`. The envelope binds schema/version, message/correlation/
causation/deal IDs, sender/recipient, mandate/key, operation/purpose/audience, UTC time,
expiry, nonce, idempotency key, canonical payload hash and signature.

A2 must reject invalid audience/recipient, unknown key, bad signature, expired message,
payload mismatch or missing mandate. A1 repeats the same validation for Quote and checks
correlation. Agent Card discovery alone never activates an agent.
