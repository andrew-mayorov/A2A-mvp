# ADR-0007: Remove A3 and use direct A1-to-A2 A2A

Status: accepted. Supersedes ADR-0001 for new deals.

## Context

The previous A3 agent relayed RFQs, collected Quotes and applied ranking while also
acting as a trust boundary. That mixed commercial agency with infrastructure control.

## Decision

A1 and A2 exchange signed A2A artifacts directly. A1 owns deterministic ranking.
Registry, mandate, policy, fraud, approval, ledger, Oracle, payment and model gateway
are bounded contexts in a modular Trusted Infrastructure monolith. They cannot select
a supplier or negotiate.

## Consequences

- fewer privileged intermediaries and clearer business accountability;
- signatures/mandates must be verified at every material boundary;
- A1 becomes responsible for resilient multi-supplier fan-out and ranking;
- trust modules can later be extracted behind ports without changing domain models;
- old A3 evidence remains historical and is never rewritten.
